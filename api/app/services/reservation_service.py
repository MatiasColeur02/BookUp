from datetime import datetime

from sqlalchemy.orm import Session

from ..persistence.models import PhysicalBookStatus, Reservation
from ..persistence.repositories import PhysicalBookRepository, ReservationRepository
from .errors import ConflictError, NotFoundError


def create_reservation(
    db: Session, *, physical_book_id: int, user_id: int, expires_at: datetime
) -> Reservation:
    physical_book_repo = PhysicalBookRepository(db)
    physical_book = physical_book_repo.get(physical_book_id)
    if physical_book is None:
        raise NotFoundError(f"Physical book {physical_book_id} not found")
    if physical_book.status != PhysicalBookStatus.available:
        raise ConflictError(f"Physical book {physical_book_id} is not available")

    physical_book.status = PhysicalBookStatus.reserved
    reservation = ReservationRepository(db).create(
        Reservation(physical_book_id=physical_book_id, user_id=user_id, expires_at=expires_at)
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def list_reservations(db: Session, library_id: int | None = None) -> list[Reservation]:
    return ReservationRepository(db).list(library_id)


def mark_picked_up(db: Session, reservation_id: int) -> Reservation:
    repo = ReservationRepository(db)
    reservation = repo.get(reservation_id)
    if reservation is None:
        raise NotFoundError(f"Reservation {reservation_id} not found")

    reservation.picked_up = True
    reservation.physical_book.status = PhysicalBookStatus.loaned
    db.commit()
    db.refresh(reservation)
    return reservation
