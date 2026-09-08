from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..models import Library, PhysicalBook, PhysicalBookStatus, Reservation


class PhysicalBookRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, physical_book_id: int) -> PhysicalBook | None:
        return self.db.get(PhysicalBook, physical_book_id)

    def list_all(
        self,
        isbn: str | None = None,
        library_id: int | None = None,
        status: PhysicalBookStatus | None = None,
    ) -> list[PhysicalBook]:
        stmt = select(PhysicalBook).order_by(PhysicalBook.id)
        if isbn is not None:
            stmt = stmt.where(PhysicalBook.isbn == isbn)
        if library_id is not None:
            stmt = stmt.where(PhysicalBook.library_id == library_id)
        if status is not None:
            stmt = stmt.where(PhysicalBook.status == status)
        return list(self.db.scalars(stmt).all())

    def create(self, physical_book: PhysicalBook) -> PhysicalBook:
        self.db.add(physical_book)
        self.db.flush()
        return physical_book

    def delete(self, physical_book: PhysicalBook) -> None:
        self.db.delete(physical_book)
        self.db.flush()

    def count_reservations(self, physical_book_id: int) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(Reservation.physical_book_id == physical_book_id)
        )

    def available_by_book(self, isbn: str) -> list[tuple[Library, list[PhysicalBook]]]:
        """Available copies of a book, grouped by the library that holds them."""
        stmt = (
            select(PhysicalBook)
            .options(joinedload(PhysicalBook.library))
            .where(PhysicalBook.isbn == isbn, PhysicalBook.status == PhysicalBookStatus.available)
        )
        physical_books = list(self.db.scalars(stmt).unique().all())

        grouped: dict[int, tuple[Library, list[PhysicalBook]]] = {}
        for physical_book in physical_books:
            _, bucket = grouped.setdefault(physical_book.library_id, (physical_book.library, []))
            bucket.append(physical_book)
        return list(grouped.values())
