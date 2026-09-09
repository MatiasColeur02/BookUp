from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    customer = "customer"
    librarian = "librarian"
    sysadmin = "sysadmin"


class PhysicalBookStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"
    loaned = "loaned"
    lost = "lost"


# Association tables for the Book <-> Author / Genre many-to-many relations.
# Pure junction tables (no attributes of their own beyond the composite PK
# described in the design doc), so plain Core Tables instead of mapped classes.
book_authors = Table(
    "book_authors",
    Base.metadata,
    Column("isbn", String(13), ForeignKey("books.isbn"), primary_key=True),
    Column("author_id", Integer, ForeignKey("authors.id"), primary_key=True),
)

book_genres = Table(
    "book_genres",
    Base.metadata,
    Column("isbn", String(13), ForeignKey("books.isbn"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id"), primary_key=True),
)


class User(Base):
    """A platform user: either a customer (patron) or library staff."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="es")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    # Set only when role == librarian: the library this user administers.
    library_id: Mapped[int | None] = mapped_column(ForeignKey("libraries.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    library: Mapped["Library | None"] = relationship(back_populates="staff")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="user")


class Library(Base):
    """A library branch."""

    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    hours: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    staff: Mapped[list["User"]] = relationship(back_populates="library")
    physical_books: Mapped[list["PhysicalBook"]] = relationship(back_populates="library")


class Book(Base):
    """Universal catalog metadata for a book, keyed by ISBN."""

    __tablename__ = "books"

    isbn: Mapped[str] = mapped_column(String(13), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    pages: Mapped[int | None] = mapped_column(Integer)
    synopsis: Mapped[str | None] = mapped_column(Text)
    # Key del objeto en S3 (`covers/<isbn>/<uuid>.jpg`), no la URL: la URL pública se
    # arma al serializar, así cambiar de bucket o poner CloudFront adelante no obliga a
    # reescribir filas. Ver `app/storage.py`.
    cover_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    authors: Mapped[list["Author"]] = relationship(secondary=book_authors, back_populates="books")
    genres: Mapped[list["Genre"]] = relationship(secondary=book_genres, back_populates="books")
    physical_books: Mapped[list["PhysicalBook"]] = relationship(back_populates="book")


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    books: Mapped[list["Book"]] = relationship(secondary=book_authors, back_populates="authors")


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    books: Mapped[list["Book"]] = relationship(secondary=book_genres, back_populates="genres")


class PhysicalBook(Base):
    """A physical copy (ejemplar) of a Book held by one Library."""

    __tablename__ = "physical_books"

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(ForeignKey("books.isbn"), nullable=False)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"), nullable=False)
    status: Mapped[PhysicalBookStatus] = mapped_column(
        Enum(PhysicalBookStatus, name="physical_book_status"),
        nullable=False,
        default=PhysicalBookStatus.available,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    book: Mapped["Book"] = relationship(back_populates="physical_books")
    library: Mapped["Library"] = relationship(back_populates="physical_books")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="physical_book")


class Reservation(Base):
    """A user's reservation of a specific physical copy.

    Lifecycle, without an explicit status enum: a reservation is *open* while
    both `cancelled_at` and `returned_at` are null, and `picked_up` tells apart
    the two open states (reserved vs. loaned). Closing it is what releases the
    copy: `cancelled_at` for a reservation dropped before pickup (by the user,
    by staff, or by expiry), `returned_at` once a picked-up copy comes back.
    """

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    physical_book_id: Mapped[int] = mapped_column(ForeignKey("physical_books.id"), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    picked_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_open(self) -> bool:
        return self.cancelled_at is None and self.returned_at is None

    user: Mapped["User"] = relationship(back_populates="reservations")
    physical_book: Mapped["PhysicalBook"] = relationship(back_populates="reservations")
