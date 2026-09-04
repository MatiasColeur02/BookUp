from sqlalchemy.orm import Session

from ..persistence.models import Book, Copy, Library
from ..persistence.repositories import BookRepository, CopyRepository
from .errors import NotFoundError


def search_books(db: Session, query: str) -> list[Book]:
    return BookRepository(db).search(query)


def get_book(db: Session, book_id: int) -> Book:
    book = BookRepository(db).get(book_id)
    if book is None:
        raise NotFoundError(f"Book {book_id} not found")
    return book


def get_availability(db: Session, book_id: int) -> tuple[Book, list[tuple[Library, list[Copy]]]]:
    book = get_book(db, book_id)
    rows = CopyRepository(db).available_by_book(book_id)
    return book, rows
