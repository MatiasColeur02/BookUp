from sqlalchemy.orm import Session

from ..persistence.models import Author, Book, Genre, Library, PhysicalBook
from ..persistence.repositories import (
    AuthorRepository,
    BookRepository,
    GenreRepository,
    PhysicalBookRepository,
)
from .errors import ConflictError, NotFoundError


def _resolve_authors(db: Session, author_ids: list[int]) -> list[Author]:
    authors = AuthorRepository(db).get_many(author_ids)
    missing = set(author_ids) - {author.id for author in authors}
    if missing:
        raise NotFoundError(f"Author {sorted(missing)[0]} not found")
    return authors


def _resolve_genres(db: Session, genre_ids: list[int]) -> list[Genre]:
    genres = GenreRepository(db).get_many(genre_ids)
    missing = set(genre_ids) - {genre.id for genre in genres}
    if missing:
        raise NotFoundError(f"Genre {sorted(missing)[0]} not found")
    return genres


def list_books(db: Session) -> list[Book]:
    return BookRepository(db).list_all()


def search_books(db: Session, query: str) -> list[Book]:
    return BookRepository(db).search(query)


def get_book(db: Session, isbn: str) -> Book:
    book = BookRepository(db).get(isbn)
    if book is None:
        raise NotFoundError(f"Book {isbn} not found")
    return book


def get_availability(db: Session, isbn: str) -> tuple[Book, list[tuple[Library, list[PhysicalBook]]]]:
    book = get_book(db, isbn)
    rows = PhysicalBookRepository(db).available_by_book(isbn)
    return book, rows


def create_book(
    db: Session,
    *,
    isbn: str,
    title: str,
    language: str,
    pages: int | None = None,
    synopsis: str | None = None,
    author_ids: list[int] | None = None,
    genre_ids: list[int] | None = None,
) -> Book:
    repo = BookRepository(db)
    if repo.get(isbn) is not None:
        raise ConflictError(f"Book {isbn} already exists")

    book = repo.create(
        Book(
            isbn=isbn,
            title=title,
            language=language,
            pages=pages,
            synopsis=synopsis,
            authors=_resolve_authors(db, author_ids or []),
            genres=_resolve_genres(db, genre_ids or []),
        )
    )
    db.commit()
    db.refresh(book)
    return book


def update_book(
    db: Session,
    isbn: str,
    *,
    title: str | None = None,
    language: str | None = None,
    pages: int | None = None,
    synopsis: str | None = None,
    author_ids: list[int] | None = None,
    genre_ids: list[int] | None = None,
) -> Book:
    book = get_book(db, isbn)

    if title is not None:
        book.title = title
    if language is not None:
        book.language = language
    if pages is not None:
        book.pages = pages
    if synopsis is not None:
        book.synopsis = synopsis
    # Sending a list replaces the whole association, it does not append to it.
    if author_ids is not None:
        book.authors = _resolve_authors(db, author_ids)
    if genre_ids is not None:
        book.genres = _resolve_genres(db, genre_ids)

    db.commit()
    db.refresh(book)
    return book


def delete_book(db: Session, isbn: str) -> None:
    repo = BookRepository(db)
    book = repo.get(isbn)
    if book is None:
        raise NotFoundError(f"Book {isbn} not found")

    if repo.count_physical_books(isbn):
        raise ConflictError(f"Book {isbn} still has physical copies")

    repo.delete(book)
    db.commit()
