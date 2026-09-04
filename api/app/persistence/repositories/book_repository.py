from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Author, Book


class BookRepository:
    """Data access for the book catalog.

    ``search`` uses a plain ILIKE scan for the MVP; in the target AWS
    architecture this query is replaced by a call to a managed search
    engine (OpenSearch) kept in sync with this table.
    """

    def __init__(self, db: Session):
        self.db = db

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
