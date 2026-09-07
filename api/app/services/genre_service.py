from sqlalchemy.orm import Session

from ..persistence.models import Genre
from ..persistence.repositories import GenreRepository
from .errors import ConflictError, NotFoundError


def list_genres(db: Session) -> list[Genre]:
    return GenreRepository(db).list_all()


def get_genre(db: Session, genre_id: int) -> Genre:
    genre = GenreRepository(db).get(genre_id)
    if genre is None:
        raise NotFoundError(f"Genre {genre_id} not found")
    return genre


def create_genre(db: Session, *, name: str) -> Genre:
    repo = GenreRepository(db)
    # Unlike authors, `Genre.name` is unique in the model.
    if repo.get_by_name(name) is not None:
        raise ConflictError(f"Genre {name!r} already exists")

    genre = repo.create(Genre(name=name))
    db.commit()
    db.refresh(genre)
    return genre


def update_genre(db: Session, genre_id: int, *, name: str | None = None) -> Genre:
    repo = GenreRepository(db)
    genre = get_genre(db, genre_id)

    if name is not None:
        existing = repo.get_by_name(name)
        if existing is not None and existing.id != genre_id:
            raise ConflictError(f"Genre {name!r} already exists")
        genre.name = name

    db.commit()
    db.refresh(genre)
    return genre


def delete_genre(db: Session, genre_id: int) -> None:
    repo = GenreRepository(db)
    genre = repo.get(genre_id)
    if genre is None:
        raise NotFoundError(f"Genre {genre_id} not found")

    if repo.count_books(genre_id):
        raise ConflictError(f"Genre {genre_id} is still linked to books")

    repo.delete(genre)
    db.commit()
