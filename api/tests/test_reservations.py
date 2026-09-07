from datetime import datetime, timedelta, timezone

import pytest

from app.persistence.models import Book, Library, PhysicalBook, User, UserRole


@pytest.fixture()
def reservation_setup(db_session):
    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    db_session.add(library)
    db_session.flush()

    book = Book(isbn="9780307474728", title="Cien años de soledad", language="es")
    db_session.add(book)
    db_session.flush()

    physical_book = PhysicalBook(isbn=book.isbn, library_id=library.id)
    user = User(
        email="reader@example.com",
        password_hash="hashed",
        name="Reader",
        role=UserRole.customer,
    )
    db_session.add_all([physical_book, user])
    db_session.commit()
    return physical_book, user


def _expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()


def test_create_reservation(client, reservation_setup):
    physical_book, user = reservation_setup
    response = client.post(
        "/reservations",
        json={
            "physical_book_id": physical_book.id,
            "user_id": user.id,
            "expires_at": _expires_at(),
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["physical_book_id"] == physical_book.id
    assert body["user_id"] == user.id
    assert body["picked_up"] is False


def test_create_reservation_physical_book_not_found(client, reservation_setup):
    _, user = reservation_setup
    response = client.post(
        "/reservations",
        json={"physical_book_id": 9999, "user_id": user.id, "expires_at": _expires_at()},
    )
    assert response.status_code == 404


def test_create_reservation_conflicts_when_not_available(client, reservation_setup):
    physical_book, user = reservation_setup
    payload = {
        "physical_book_id": physical_book.id,
        "user_id": user.id,
        "expires_at": _expires_at(),
    }
    first = client.post("/reservations", json=payload)
    assert first.status_code == 201

    second = client.post("/reservations", json=payload)
    assert second.status_code == 409


def test_list_reservations(client, reservation_setup):
    physical_book, user = reservation_setup
    client.post(
        "/reservations",
        json={
            "physical_book_id": physical_book.id,
            "user_id": user.id,
            "expires_at": _expires_at(),
        },
    )

    response = client.get("/reservations")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_reservations_filtered_by_library(client, reservation_setup, db_session):
    physical_book, user = reservation_setup
    other_library = Library(name="Norte", address="Calle 2", state="SF", city="Rosario")
    db_session.add(other_library)
    db_session.commit()

    client.post(
        "/reservations",
        json={
            "physical_book_id": physical_book.id,
            "user_id": user.id,
            "expires_at": _expires_at(),
        },
    )

    response = client.get("/reservations", params={"library_id": other_library.id})
    assert response.status_code == 200
    assert response.json() == []

    response = client.get("/reservations", params={"library_id": physical_book.library_id})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_reservation(client, reservation_setup):
    physical_book, user = reservation_setup
    created = client.post(
        "/reservations",
        json={
            "physical_book_id": physical_book.id,
            "user_id": user.id,
            "expires_at": _expires_at(),
        },
    ).json()

    response = client.get(f"/reservations/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_reservation_not_found(client):
    response = client.get("/reservations/9999")
    assert response.status_code == 404


def test_mark_picked_up(client, reservation_setup):
    physical_book, user = reservation_setup
    created = client.post(
        "/reservations",
        json={
            "physical_book_id": physical_book.id,
            "user_id": user.id,
            "expires_at": _expires_at(),
        },
    ).json()

    response = client.patch(f"/reservations/{created['id']}/pickup")
    assert response.status_code == 200
    assert response.json()["picked_up"] is True


def test_mark_picked_up_not_found(client):
    response = client.patch("/reservations/9999/pickup")
    assert response.status_code == 404
