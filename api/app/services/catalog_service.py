from sqlalchemy.orm import Session

from ..persistence.models import Book, Library, PhysicalBook
from ..persistence.repositories import BookRepository, PhysicalBookRepository
from .errors import NotFoundError


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
