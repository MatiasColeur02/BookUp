"""Fixtures de los tests de repositories contra DynamoDB Local."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.persistence.entities import (
    Author,
    Book,
    Genre,
    Library,
    PhysicalBook,
    Reservation,
    User,
    UserRole,
)
from app.persistence.dynamo_repositories import (
    AuthorRepository,
    BookRepository,
    GenreRepository,
    LibraryRepository,
    PhysicalBookRepository,
    ReservationRepository,
    UserRepository,
)

from ..dynamo_support import temporary_dynamo

ISBN = "9780307474728"


@pytest.fixture()
def db():
    """Una tabla `bookup` con sus 4 GSIs, vacía y exclusiva de este test."""
    yield from temporary_dynamo(create_table=True)


class Factory:
    """Atajos para armar el estado que un test necesita, pasando por los repositories."""

    def __init__(self, db):
        self.db = db
        self._n = 0

    def _next(self) -> int:
        self._n += 1
        return self._n

    def author(self, name: str | None = None) -> Author:
        return AuthorRepository(self.db).create(Author(name=name or f"Author {self._next()}"))

    def genre(self, name: str | None = None) -> Genre:
        return GenreRepository(self.db).create(Genre(name=name or f"Genre {self._next()}"))

    def library(self, name: str | None = None, city: str = "Rosario", **extra) -> Library:
        n = self._next()
        return LibraryRepository(self.db).create(
            Library(
                name=name or f"Library {n}",
                address=f"Calle {n}",
                state="Santa Fe",
                city=city,
                **extra,
            )
        )

    def book(
        self,
        isbn: str = ISBN,
        title: str = "Cien años de soledad",
        authors: list[Author] | None = None,
        genres: list[Genre] | None = None,
        **extra,
    ) -> Book:
        return BookRepository(self.db).create(
            Book(
                isbn=isbn,
                title=title,
                language="es",
                authors=authors or [],
                genres=genres or [],
                **extra,
            )
        )

    def copy(self, isbn: str = ISBN, library: Library | None = None) -> PhysicalBook:
        library = library or self.library()
        return PhysicalBookRepository(self.db).create(
            PhysicalBook(isbn=isbn, library_id=library.id)
        )

    def user(
        self,
        email: str | None = None,
        role: UserRole = UserRole.customer,
        library_id: int | None = None,
        name: str | None = None,
    ) -> User:
        n = self._next()
        return UserRepository(self.db).create(
            User(
                email=email or f"user{n}@example.com",
                password_hash="hash",
                name=name or f"User {n}",
                role=role,
                library_id=library_id,
            )
        )

    def reservation(
        self,
        copy: PhysicalBook | None = None,
        user: User | None = None,
        expires_in: timedelta = timedelta(days=3),
    ) -> Reservation:
        copy = copy or self.copy()
        user = user or self.user()
        return ReservationRepository(self.db).create(
            Reservation(
                user_id=user.id,
                physical_book_id=copy.id,
                expires_at=datetime.now(timezone.utc) + expires_in,
            )
        )


@pytest.fixture()
def make(db) -> Factory:
    return Factory(db)
