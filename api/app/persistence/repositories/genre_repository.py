from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Genre, book_genres


class GenreRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Genre]:
        return list(self.db.scalars(select(Genre).order_by(Genre.name)).all())

    def get(self, genre_id: int) -> Genre | None:
        return self.db.get(Genre, genre_id)

    def get_by_name(self, name: str) -> Genre | None:
        return self.db.scalar(select(Genre).where(Genre.name == name))

    def get_many(self, genre_ids: list[int]) -> list[Genre]:
        if not genre_ids:
            return []
        return list(self.db.scalars(select(Genre).where(Genre.id.in_(genre_ids))).all())

    def create(self, genre: Genre) -> Genre:
        self.db.add(genre)
        self.db.flush()
        return genre

    def delete(self, genre: Genre) -> None:
        self.db.delete(genre)
        self.db.flush()

    def count_books(self, genre_id: int) -> int:
        return self.db.scalar(
            select(func.count()).select_from(book_genres).where(book_genres.c.genre_id == genre_id)
        )
