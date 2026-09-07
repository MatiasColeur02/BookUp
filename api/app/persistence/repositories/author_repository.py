from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Author, book_authors


class AuthorRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Author]:
        return list(self.db.scalars(select(Author).order_by(Author.name)).all())

    def get(self, author_id: int) -> Author | None:
        return self.db.get(Author, author_id)

    def get_by_name(self, name: str) -> Author | None:
        return self.db.scalar(select(Author).where(Author.name == name))

    def get_many(self, author_ids: list[int]) -> list[Author]:
        if not author_ids:
            return []
        return list(self.db.scalars(select(Author).where(Author.id.in_(author_ids))).all())

    def create(self, author: Author) -> Author:
        self.db.add(author)
        self.db.flush()
        return author

    def delete(self, author: Author) -> None:
        self.db.delete(author)
        self.db.flush()

    def count_books(self, author_id: int) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(book_authors)
            .where(book_authors.c.author_id == author_id)
        )
