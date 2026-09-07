from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Author, Book, PhysicalBook


class BookRepository:
    """Data access for the book catalog.

    ``search`` uses a plain ILIKE scan for the MVP; in the target AWS
    architecture this query is replaced by a call to a managed search
    engine (OpenSearch) kept in sync with this table.
    """

    def __init__(self, db: Session):
        self.db = db

    def list_all(self, limit: int = 100) -> list[Book]:
        return list(self.db.scalars(select(Book).order_by(Book.title).limit(limit)).all())

    def search(self, query: str, limit: int = 50) -> list[Book]:
        pattern = f"%{query}%"
        stmt = (
            select(Book)
            .outerjoin(Book.authors)
            .where(
                or_(
                    Book.title.ilike(pattern),
                    Book.isbn.ilike(pattern),
                    Book.synopsis.ilike(pattern),
                    Author.name.ilike(pattern),
                )
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

    def get(self, isbn: str) -> Book | None:
        return self.db.get(Book, isbn)

    def create(self, book: Book) -> Book:
        self.db.add(book)
        self.db.flush()
        return book

    def delete(self, book: Book) -> None:
        self.db.delete(book)
        self.db.flush()

    def count_physical_books(self, isbn: str) -> int:
        return self.db.scalar(
            select(func.count()).select_from(PhysicalBook).where(PhysicalBook.isbn == isbn)
        )
