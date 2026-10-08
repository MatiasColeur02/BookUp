from ..persistence.dynamo import Dynamo
from ..persistence.entities import Author
from ..persistence.errors import ConditionFailedError
from ..persistence.repositories import AuthorRepository
from .errors import ConflictError, NotFoundError


def list_authors(db: Dynamo) -> list[Author]:
    return AuthorRepository(db).list_all()


def get_author(db: Dynamo, author_id: int) -> Author:
    author = AuthorRepository(db).get(author_id)
    if author is None:
        raise NotFoundError(f"Author {author_id} not found")
    return author


def create_author(db: Dynamo, *, name: str) -> Author:
    # `Author.name` is deliberately not unique: two different people can publish
    # under the same name, so homonyms are allowed and the id is the only identity.
    return AuthorRepository(db).create(Author(name=name))


def update_author(db: Dynamo, author_id: int, *, name: str | None = None) -> Author:
    author = get_author(db, author_id)
    if name is None:
        return author
    try:
        return AuthorRepository(db).update(author_id, name=name)
    except ConditionFailedError as exc:  # deleted between the read and the write
        raise NotFoundError(f"Author {author_id} not found") from exc


def delete_author(db: Dynamo, author_id: int) -> None:
    repo = AuthorRepository(db)
    author = repo.get(author_id)
    if author is None:
        raise NotFoundError(f"Author {author_id} not found")
    if repo.has_books(author_id):
        raise ConflictError(f"Author {author_id} is still linked to books")
    repo.delete(author)
