from datetime import datetime

from sqlalchemy.orm import Session

from ..persistence.models import PhysicalBookStatus, Reservation, User, UserRole
from ..persistence.repositories import PhysicalBookRepository, ReservationRepository
from .errors import ConflictError, ForbiddenError, NotFoundError


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
    db: Session, *, viewer: User, library_id: int | None = None
) -> list[Reservation]:
    repo = ReservationRepository(db)

    if viewer.role is UserRole.sysadmin:
        return repo.list(library_id=library_id)

    if viewer.role is UserRole.librarian:
        if viewer.library_id is None:
            raise ForbiddenError("This librarian is not assigned to any library")
        if library_id is not None and library_id != viewer.library_id:
            raise ForbiddenError("You can only list reservations of your own library")
        return repo.list(library_id=viewer.library_id)

    # A customer only ever sees their own reservations.
    return repo.list(library_id=library_id, user_id=viewer.id)


def mark_picked_up(db: Session, reservation_id: int, *, viewer: User) -> Reservation:
    reservation = _get_or_404(db, reservation_id)
    _assert_can_manage(viewer, reservation)

    reservation.picked_up = True
    reservation.physical_book.status = PhysicalBookStatus.loaned
    db.commit()
    db.refresh(reservation)
    return reservation
