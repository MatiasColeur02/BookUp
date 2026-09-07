from sqlalchemy.orm import Session

from ..persistence.models import Author
from ..persistence.repositories import AuthorRepository
from .errors import ConflictError, NotFoundError


def list_authors(db: Session) -> list[Author]:
    return AuthorRepository(db).list_all()


def get_author(db: Session, author_id: int) -> Author:
    author = AuthorRepository(db).get(author_id)
    if author is None:
        raise NotFoundError(f"Author {author_id} not found")
    return author


def create_author(db: Session, *, name: str) -> Author:
    # `Author.name` is deliberately not unique in the model: two different
    # people can publish under the same name, so homonyms are allowed and the
    # id is the only identity.
    author = AuthorRepository(db).create(Author(name=name))
    db.commit()
    db.refresh(author)
    return author


def update_author(db: Session, author_id: int, *, name: str | None = None) -> Author:
    author = get_author(db, author_id)

    if name is not None:
        author.name = name

    db.commit()
    db.refresh(author)
    return author


def delete_author(db: Session, author_id: int) -> None:
    repo = AuthorRepository(db)
    author = repo.get(author_id)
    if author is None:
        raise NotFoundError(f"Author {author_id} not found")

    if repo.count_books(author_id):
        raise ConflictError(f"Author {author_id} is still linked to books")

    repo.delete(author)
    db.commit()
