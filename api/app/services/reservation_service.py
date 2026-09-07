from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..persistence.models import PhysicalBook, PhysicalBookStatus, Reservation, User, UserRole
from ..persistence.repositories import PhysicalBookRepository, ReservationRepository
from .errors import ConflictError, ForbiddenError, NotFoundError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_404(db: Session, reservation_id: int) -> Reservation:
    reservation = ReservationRepository(db).get(reservation_id)
    if reservation is None:
        raise NotFoundError(f"Reservation {reservation_id} not found")
    return reservation


def _assert_can_manage(viewer: User, reservation: Reservation) -> None:
    """Staff-side operations: the librarian of the branch holding the copy, or a sysadmin."""
    if viewer.role is UserRole.sysadmin:
        return
    if (
        viewer.role is UserRole.librarian
        and viewer.library_id == reservation.physical_book.library_id
    ):
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


def close_open_reservation(
    db: Session, physical_book: PhysicalBook, *, at: datetime | None = None
) -> Reservation | None:
    """Close the open reservation of a copy, if there is one. Does not commit.

    Used when a copy leaves circulation outside the normal flow (marked `lost`):
    a picked-up reservation is closed as returned, one still waiting for pickup
    as cancelled.
    """
    reservation = ReservationRepository(db).get_open_for_physical_book(physical_book.id)
    if reservation is None:
        return None

    when = at or _now()
    if reservation.picked_up:
        reservation.returned_at = when
    else:
        reservation.cancelled_at = when
    return reservation


def create_reservation(
    db: Session, *, physical_book_id: int, user: User, expires_at: datetime
) -> Reservation:
    physical_book_repo = PhysicalBookRepository(db)
    physical_book = physical_book_repo.get(physical_book_id)
    if physical_book is None:
        raise NotFoundError(f"Physical book {physical_book_id} not found")
    if physical_book.status != PhysicalBookStatus.available:
        raise ConflictError(f"Physical book {physical_book_id} is not available")

    physical_book.status = PhysicalBookStatus.reserved
    reservation = ReservationRepository(db).create(
        Reservation(physical_book_id=physical_book_id, user_id=user.id, expires_at=expires_at)
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def get_reservation(db: Session, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_view(viewer, reservation)
    return reservation


def list_reservations(
    db: Session, *, viewer: User, library_id: int | None = None, is_open: bool | None = None
) -> list[Reservation]:
    repo = ReservationRepository(db)

    if viewer.role is UserRole.sysadmin:
        return repo.list(library_id=library_id, is_open=is_open)

    if viewer.role is UserRole.librarian:
        if viewer.library_id is None:
            raise ForbiddenError("This librarian is not assigned to any library")
        if library_id is not None and library_id != viewer.library_id:
            raise ForbiddenError("You can only list reservations of your own library")
        return repo.list(library_id=viewer.library_id, is_open=is_open)

    # A customer only ever sees their own reservations.
    return repo.list(library_id=library_id, user_id=viewer.id, is_open=is_open)


def update_reservation(
    db: Session, reservation_id: int, *, viewer: User, expires_at: datetime | None = None
) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_manage(viewer, reservation)
    _assert_open(reservation)

    if reservation.picked_up:
        raise ConflictError(f"Reservation {reservation_id} was already picked up")

    if expires_at is not None:
        reservation.expires_at = expires_at

    db.commit()
    db.refresh(reservation)
    return reservation


def mark_picked_up(db: Session, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_manage(viewer, reservation)
    _assert_open(reservation)

    if reservation.picked_up:
        raise ConflictError(f"Reservation {reservation_id} was already picked up")

    reservation.picked_up = True
    reservation.physical_book.status = PhysicalBookStatus.loaned
    db.commit()
    db.refresh(reservation)
    return reservation


def cancel_reservation(db: Session, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_view(viewer, reservation)
    _assert_open(reservation)

    if reservation.picked_up:
        raise ConflictError(
            f"Reservation {reservation_id} was already picked up: return it instead"
        )

    reservation.cancelled_at = _now()
    reservation.physical_book.status = PhysicalBookStatus.available
    db.commit()
    db.refresh(reservation)
    return reservation


def mark_returned(db: Session, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_manage(viewer, reservation)
    _assert_open(reservation)

    if not reservation.picked_up:
        raise ConflictError(
            f"Reservation {reservation_id} was never picked up: cancel it instead"
        )

    reservation.returned_at = _now()
    reservation.physical_book.status = PhysicalBookStatus.available
    db.commit()
    db.refresh(reservation)
    return reservation


def expire_reservations(db: Session, now: datetime | None = None) -> int:
    """Release copies held by reservations that expired without being picked up.

    Idempotent: a second run finds nothing left to expire. Meant to be driven by
    a scheduler (EventBridge in the target architecture).
    """
    when = now or _now()
    expired = ReservationRepository(db).list_expired(when)

    for reservation in expired:
        reservation.cancelled_at = when
        # A copy already marked `lost` stays lost; only release the held ones.
        if reservation.physical_book.status is PhysicalBookStatus.reserved:
            reservation.physical_book.status = PhysicalBookStatus.available

    db.commit()
    return len(expired)
