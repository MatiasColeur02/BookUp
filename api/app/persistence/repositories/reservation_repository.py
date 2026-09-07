from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PhysicalBook, Reservation


class ReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, reservation: Reservation) -> Reservation:
        self.db.add(reservation)
        self.db.flush()
        return reservation

    def get(self, reservation_id: int) -> Reservation | None:
        return self.db.get(Reservation, reservation_id)

    def list(
        self, library_id: int | None = None, user_id: int | None = None
    ) -> list[Reservation]:
        stmt = select(Reservation).join(PhysicalBook)
        if library_id is not None:
            stmt = stmt.where(PhysicalBook.library_id == library_id)
        if user_id is not None:
            stmt = stmt.where(Reservation.user_id == user_id)
        return list(self.db.scalars(stmt).all())
