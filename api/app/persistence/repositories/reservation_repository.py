from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PhysicalBook, Reservation


def _open(stmt):
    """Restrict a statement to reservations that are neither cancelled nor returned."""
    return stmt.where(Reservation.cancelled_at.is_(None), Reservation.returned_at.is_(None))


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, reservation: Reservation) -> Reservation:
        self.db.add(reservation)
        self.db.flush()
        return reservation

    def get(self, reservation_id: int) -> Reservation | None:
        return self.db.get(Reservation, reservation_id)

    def list_all(
        self,
        library_id: int | None = None,
        user_id: int | None = None,
        is_open: bool | None = None,
    ) -> list[Reservation]:
        stmt = select(Reservation).join(PhysicalBook)
        if library_id is not None:
            stmt = stmt.where(PhysicalBook.library_id == library_id)
        if user_id is not None:
            stmt = stmt.where(Reservation.user_id == user_id)
        if is_open is True:
            stmt = _open(stmt)
        elif is_open is False:
            stmt = stmt.where(
                Reservation.cancelled_at.is_not(None) | Reservation.returned_at.is_not(None)
            )
        return list(self.db.scalars(stmt).all())

    def get_open_for_physical_book(self, physical_book_id: int) -> Reservation | None:
        stmt = _open(select(Reservation).where(
            Reservation.physical_book_id == physical_book_id
        ))
        return self.db.scalars(stmt).first()

    def list_expired(self, now: datetime) -> list[Reservation]:
        """Open reservations past their expiry that were never picked up."""
        stmt = _open(
            select(Reservation).where(
                Reservation.expires_at < now,
                Reservation.picked_up.is_(False),
            )
        )
        return list(self.db.scalars(stmt).all())
