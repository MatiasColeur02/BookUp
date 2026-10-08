from datetime import datetime, timezone

from ..persistence.dynamo import Dynamo
from ..persistence.entities import PhysicalBookStatus, Reservation, User, UserRole
from ..persistence.errors import ConditionFailedError
from ..persistence.repositories import PhysicalBookRepository, ReservationRepository
from .errors import ConflictError, ForbiddenError, NotFoundError

# Every transition below reads first and then writes, but the reads are only there to
# give a precise message. What keeps two requests from both winning is the condition of
# the write inside the repository: the loser gets `ConditionFailedError`, and it is
# translated to the same 409 as the pre-check.


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_404(db: Dynamo, reservation_id: int) -> Reservation:
    reservation = ReservationRepository(db).get(reservation_id)
    if reservation is None:
        raise NotFoundError(f"Reservation {reservation_id} not found")
    return reservation


def _assert_can_manage(viewer: User, reservation: Reservation) -> None:
    """Staff-side operations: the librarian of the branch holding the copy, or a sysadmin.

    `reservation.library_id` is copied from the copy when the reservation is made, so
    authorizing needs no read of the copy.
    """
    if viewer.role is UserRole.sysadmin:
        return
    if viewer.role is UserRole.librarian and viewer.library_id == reservation.library_id:
        return
    raise ForbiddenError(f"You are not allowed to manage reservation {reservation.id}")


def _assert_can_view(viewer: User, reservation: Reservation) -> None:
    if viewer.id == reservation.user_id:
        return
    _assert_can_manage(viewer, reservation)


def _assert_open(reservation: Reservation) -> None:
    if reservation.cancelled_at is not None:
        raise ConflictError(f"Reservation {reservation.id} is already cancelled")
    if reservation.returned_at is not None:
        raise ConflictError(f"Reservation {reservation.id} was already returned")


def create_reservation(
    db: Dynamo, *, physical_book_id: int, user: User, expires_at: datetime
) -> Reservation:
    physical_book = PhysicalBookRepository(db).get(physical_book_id)
    if physical_book is None:
        raise NotFoundError(f"Physical book {physical_book_id} not found")
    if physical_book.status != PhysicalBookStatus.available:
        raise ConflictError(f"Physical book {physical_book_id} is not available")

    try:
        return ReservationRepository(db).create(
            Reservation(physical_book_id=physical_book_id, user_id=user.id, expires_at=expires_at)
        )
    except ConditionFailedError as exc:  # somebody else reserved it first
        raise ConflictError(f"Physical book {physical_book_id} is not available") from exc


def get_reservation(db: Dynamo, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_view(viewer, reservation)
    return reservation


def list_reservations(
    db: Dynamo,
    *,
    viewer: User,
    library_id: int | None = None,
    is_open: bool | None = None,
    mine: bool = False,
) -> list[Reservation]:
    repo = ReservationRepository(db)

    # "Las mías" no depende del rol: un librarian puede reservar en cualquier sede, y
    # sin esto no tendría forma de listar sus propias reservas — el alcance por rol lo
    # acotaría a su sede. No expone nada nuevo: el dueño ya puede ver cada una por id.
    if mine:
        return repo.list_all(library_id=library_id, user_id=viewer.id, is_open=is_open)

    if viewer.role is UserRole.sysadmin:
        return repo.list_all(library_id=library_id, is_open=is_open)

    if viewer.role is UserRole.librarian:
        if viewer.library_id is None:
            raise ForbiddenError("This librarian is not assigned to any library")
        if library_id is not None and library_id != viewer.library_id:
            raise ForbiddenError("You can only list reservations of your own library")
        return repo.list_all(library_id=viewer.library_id, is_open=is_open)

    # A customer only ever sees their own reservations.
    return repo.list_all(library_id=library_id, user_id=viewer.id, is_open=is_open)


def update_reservation(
    db: Dynamo, reservation_id: int, *, viewer: User, expires_at: datetime | None = None
) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_manage(viewer, reservation)
    _assert_open(reservation)

    if reservation.picked_up:
        raise ConflictError(f"Reservation {reservation_id} was already picked up")
    if expires_at is None:
        return reservation

    try:
        return ReservationRepository(db).update_expiry(reservation_id, expires_at)
    except ConditionFailedError as exc:
        raise ConflictError(str(exc)) from exc


def mark_picked_up(db: Dynamo, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_manage(viewer, reservation)
    _assert_open(reservation)

    if reservation.picked_up:
        raise ConflictError(f"Reservation {reservation_id} was already picked up")

    try:
        return ReservationRepository(db).mark_picked_up(reservation_id)
    except ConditionFailedError as exc:
        raise ConflictError(str(exc)) from exc


def cancel_reservation(db: Dynamo, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_view(viewer, reservation)
    _assert_open(reservation)

    if reservation.picked_up:
        raise ConflictError(
            f"Reservation {reservation_id} was already picked up: return it instead"
        )

    try:
        return ReservationRepository(db).cancel(reservation_id, _now())
    except ConditionFailedError as exc:
        raise ConflictError(str(exc)) from exc


def mark_returned(db: Dynamo, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_manage(viewer, reservation)
    _assert_open(reservation)

    if not reservation.picked_up:
        raise ConflictError(
            f"Reservation {reservation_id} was never picked up: cancel it instead"
        )

    try:
        return ReservationRepository(db).mark_returned(reservation_id, _now())
    except ConditionFailedError as exc:
        raise ConflictError(str(exc)) from exc


def expire_reservations(db: Dynamo, now: datetime | None = None) -> int:
    """Release copies held by reservations that expired without being picked up.

    Idempotent: a second run finds nothing left to expire. Meant to be driven by
    a scheduler (EventBridge in the target architecture). A reservation picked up or
    cancelled between the listing and the write is skipped by the repository, not
    expired by mistake. The listing is a Query on the sparse index of open reservations,
    so it walks dozens of items, not the whole history.
    """
    when = now or _now()
    repo = ReservationRepository(db)
    return repo.expire([reservation.id for reservation in repo.list_expired(when)], when)
