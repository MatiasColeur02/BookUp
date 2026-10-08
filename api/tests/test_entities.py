"""`persistence/entities.py`: dataclasses en lugar de entidades ORM."""

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app.controllers.schemas import (
    AuthorOut,
    BookOut,
    GenreOut,
    LibraryOut,
    PhysicalBookOut,
    ReservationOut,
    UserOut,
)
from app.persistence import entities

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_enum_values_are_the_stored_strings():
    assert {r.value for r in entities.UserRole} == {"customer", "librarian", "sysadmin"}
    assert {s.value for s in entities.PhysicalBookStatus} == {
        "available",
        "reserved",
        "loaned",
        "lost",
    }


def test_entities_are_immutable():
    author = entities.Author(name="Borges", id=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        author.name = "Cortázar"
    assert dataclasses.replace(author, name="Cortázar").name == "Cortázar"
    assert author.name == "Borges"


def test_persistence_assigned_fields_start_empty():
    reservation = entities.Reservation(user_id=1, physical_book_id=2, expires_at=NOW)
    assert reservation.id is None and reservation.reserved_at is None
    assert reservation.library_id is None and reservation.isbn is None
    assert reservation.picked_up is False

    copy = entities.PhysicalBook(isbn="9780307474728", library_id=1)
    assert copy.status is entities.PhysicalBookStatus.available
    assert copy.open_reservation_id is None


@pytest.mark.parametrize(
    "cancelled_at, returned_at, expected",
    [
        (None, None, True),
        (NOW, None, False),
        (None, NOW, False),
        (NOW, NOW, False),
    ],
)
def test_reservation_is_open_until_cancelled_or_returned(cancelled_at, returned_at, expected):
    reservation = entities.Reservation(
        user_id=1,
        physical_book_id=1,
        expires_at=NOW + timedelta(days=1),
        cancelled_at=cancelled_at,
        returned_at=returned_at,
    )
    assert reservation.is_open is expected


def test_book_collections_are_not_shared_between_instances():
    a = entities.Book(isbn="1", title="A", language="es")
    b = entities.Book(isbn="2", title="B", language="es")
    assert a.authors == [] and a.authors is not b.authors


# Los esquemas leen las entidades con `from_attributes`. Que funcione igual sobre
# dataclasses es lo que deja a los controllers sin tocar (ROADMAP §7.3).


def test_book_out_from_a_dataclass_with_embedded_authors_and_genres():
    book = entities.Book(
        isbn="9780307474728",
        title="Cien años de soledad",
        language="es",
        pages=417,
        authors=[entities.Author(id=1, name="Gabriel García Márquez")],
        genres=[entities.Genre(id=2, name="Novela")],
    )
    out = BookOut.from_book(book)
    assert out.title == "Cien años de soledad"
    assert out.authors == [AuthorOut(id=1, name="Gabriel García Márquez")]
    assert out.genres == [GenreOut(id=2, name="Novela")]
    assert out.cover_url is None  # sin S3_BUCKET la feature está apagada


def test_physical_book_out_from_a_dataclass_accepts_the_shared_enum():
    copy = entities.PhysicalBook(
        id=7, isbn="9780307474728", library_id=3, status=entities.PhysicalBookStatus.loaned
    )
    out = PhysicalBookOut.model_validate(copy)
    assert out.status is entities.PhysicalBookStatus.loaned


def test_other_outputs_validate_from_dataclasses():
    library = entities.Library(id=1, name="Central", address="X 1", state="BA", city="CABA")
    assert LibraryOut.model_validate(library).city == "CABA"

    user = entities.User(
        id=1, email="a@b.com", password_hash="x", name="Ana", role=entities.UserRole.customer
    )
    out = UserOut.model_validate(user)
    assert out.role is entities.UserRole.customer and out.library_id is None
    assert not hasattr(out, "password_hash")

    reservation = entities.Reservation(
        id=1, user_id=1, physical_book_id=2, expires_at=NOW, reserved_at=NOW
    )
    assert ReservationOut.model_validate(reservation).physical_book_id == 2
