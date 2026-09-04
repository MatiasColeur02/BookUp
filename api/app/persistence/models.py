from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class CopyStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"
    loaned = "loaned"


class ReservationStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    fulfilled = "fulfilled"


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300))

    copies: Mapped[list["Copy"]] = relationship(back_populates="library")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    isbn: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    synopsis: Mapped[str | None] = mapped_column(Text)

    copies: Mapped[list["Copy"]] = relationship(back_populates="book")


class Copy(Base):
    """A physical copy of a Book held by one Library (ejemplar)."""

    __tablename__ = "copies"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"), nullable=False)
    status: Mapped[CopyStatus] = mapped_column(
        Enum(CopyStatus, name="copy_status"), default=CopyStatus.available, nullable=False
    )

    book: Mapped["Book"] = relationship(back_populates="copies")
    library: Mapped["Library"] = relationship(back_populates="copies")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="copy")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(ForeignKey("copies.id"), nullable=False)
    patron_name: Mapped[str] = mapped_column(String(200), nullable=False)
    patron_email: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status"),
        default=ReservationStatus.pending,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set when a librarian confirms the reservation in person. TODO: replace
    # with an authenticated librarian_id once the librarian portal has auth.
    confirmed_by: Mapped[str | None] = mapped_column(String(200))

    copy: Mapped["Copy"] = relationship(back_populates="reservations")
