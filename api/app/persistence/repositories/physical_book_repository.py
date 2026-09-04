from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import Library, PhysicalBook, PhysicalBookStatus


class PhysicalBookRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, physical_book_id: int) -> PhysicalBook | None:
        return self.db.get(PhysicalBook, physical_book_id)

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
