from ..persistence.dynamo import Dynamo
from ..persistence.entities import Genre
from ..persistence.errors import AlreadyExistsError, ConditionFailedError
from ..persistence.repositories import GenreRepository
from .errors import ConflictError, NotFoundError


def list_genres(db: Dynamo) -> list[Genre]:
    return GenreRepository(db).list_all()


def get_genre(db: Dynamo, genre_id: int) -> Genre:
    genre = GenreRepository(db).get(genre_id)
    if genre is None:
        raise NotFoundError(f"Genre {genre_id} not found")
    return genre


def create_genre(db: Dynamo, *, name: str) -> Genre:
    repo = GenreRepository(db)
    # Unlike authors, `Genre.name` is unique. The pre-check gives the usual message; the
    # uniqueness itself is enforced by the repository, so a concurrent create also loses.
    if repo.get_by_name(name) is not None:
        raise ConflictError(f"Genre {name!r} already exists")
    try:
        return repo.create(Genre(name=name))
    except AlreadyExistsError as exc:
        raise ConflictError(f"Genre {name!r} already exists") from exc


def update_genre(db: Dynamo, genre_id: int, *, name: str | None = None) -> Genre:
    repo = GenreRepository(db)
    genre = get_genre(db, genre_id)
    if name is None:
        return genre

    existing = repo.get_by_name(name)
    if existing is not None and existing.id != genre_id:
        raise ConflictError(f"Genre {name!r} already exists")
    try:
        return repo.update(genre_id, name=name)
    except AlreadyExistsError as exc:
        raise ConflictError(f"Genre {name!r} already exists") from exc
    except ConditionFailedError as exc:  # deleted or renamed by someone else meanwhile
        raise NotFoundError(f"Genre {genre_id} not found") from exc


def delete_genre(db: Dynamo, genre_id: int) -> None:
    repo = GenreRepository(db)
    genre = repo.get(genre_id)
    if genre is None:
        raise NotFoundError(f"Genre {genre_id} not found")
    if repo.has_books(genre_id):
        raise ConflictError(f"Genre {genre_id} is still linked to books")
    repo.delete(genre)
