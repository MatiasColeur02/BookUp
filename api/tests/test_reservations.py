from datetime import datetime, timedelta, timezone

import pytest

from app.persistence.models import Book, Library, PhysicalBook, UserRole


@pytest.fixture()
def reservation_setup(db_session, make_user):
    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    db_session.add(library)
    db_session.flush()

    book = Book(isbn="9780307474728", title="Cien años de soledad", language="es")
    db_session.add(book)
    db_session.flush()

    physical_book = PhysicalBook(isbn=book.isbn, library_id=library.id)
    db_session.add(physical_book)
    db_session.commit()
    db_session.refresh(physical_book)

    user = make_user(UserRole.customer)
    return physical_book, user


def _expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()


def _reserve(client, headers, physical_book_id):
    return client.post(
        "/reservations",
        json={"physical_book_id": physical_book_id, "expires_at": _expires_at()},
        headers=headers,
    )


def test_create_reservation(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    response = _reserve(client, auth_headers(user), physical_book.id)

    assert response.status_code == 201
    body = response.json()
    assert body["physical_book_id"] == physical_book.id
    # The owner comes from the token, not from the request body.
    assert body["user_id"] == user.id
    assert body["picked_up"] is False


def test_create_reservation_requires_a_token(client, reservation_setup):
    physical_book, _ = reservation_setup
    response = client.post(
        "/reservations",
        json={"physical_book_id": physical_book.id, "expires_at": _expires_at()},
    )
    assert response.status_code == 401


def test_create_reservation_physical_book_not_found(client, reservation_setup, auth_headers):
    _, user = reservation_setup
    response = _reserve(client, auth_headers(user), 9999)
    assert response.status_code == 404


def test_create_reservation_conflicts_when_not_available(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    headers = auth_headers(user)

    assert _reserve(client, headers, physical_book.id).status_code == 201
    assert _reserve(client, headers, physical_book.id).status_code == 409


def test_list_reservations_as_sysadmin(client, reservation_setup, auth_headers, sysadmin_headers):
    physical_book, user = reservation_setup
    _reserve(client, auth_headers(user), physical_book.id)

    response = client.get("/reservations", headers=sysadmin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_reservations_filtered_by_library(
    client, reservation_setup, auth_headers, sysadmin_headers, db_session
):
    physical_book, user = reservation_setup
    other_library = Library(name="Norte", address="Calle 2", state="SF", city="Rosario")
    db_session.add(other_library)
    db_session.commit()

    _reserve(client, auth_headers(user), physical_book.id)

    response = client.get(
        "/reservations", params={"library_id": other_library.id}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert response.json() == []

    response = client.get(
        "/reservations", params={"library_id": physical_book.library_id}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_customer_only_lists_their_own_reservations(
    client, reservation_setup, auth_headers, make_user
):
    physical_book, user = reservation_setup
    _reserve(client, auth_headers(user), physical_book.id)

    other_customer = make_user(UserRole.customer)
    response = client.get("/reservations", headers=auth_headers(other_customer))
    assert response.status_code == 200
    assert response.json() == []

    response = client.get("/reservations", headers=auth_headers(user))
    assert len(response.json()) == 1


def test_librarian_lists_only_their_own_library(
    client, reservation_setup, auth_headers, make_user
):
    physical_book, user = reservation_setup
    _reserve(client, auth_headers(user), physical_book.id)

    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    response = client.get("/reservations", headers=auth_headers(librarian))
    assert response.status_code == 200
    assert len(response.json()) == 1

    # Asking for someone else's branch is refused rather than silently empty.
    response = client.get(
        "/reservations", params={"library_id": 9999}, headers=auth_headers(librarian)
    )
    assert response.status_code == 403


def test_get_reservation_as_owner(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    response = client.get(f"/reservations/{created['id']}", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json() == created


def test_get_reservation_forbidden_for_another_customer(
    client, reservation_setup, auth_headers, make_user
):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    other = make_user(UserRole.customer)
    response = client.get(f"/reservations/{created['id']}", headers=auth_headers(other))
    assert response.status_code == 403


def test_get_reservation_not_found(client, sysadmin_headers):
    response = client.get("/reservations/9999", headers=sysadmin_headers)
    assert response.status_code == 404


def test_mark_picked_up(client, reservation_setup, auth_headers, make_user):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    response = client.patch(
        f"/reservations/{created['id']}/pickup", headers=auth_headers(librarian)
    )
    assert response.status_code == 200
    assert response.json()["picked_up"] is True


def test_mark_picked_up_forbidden_for_the_customer(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    response = client.patch(f"/reservations/{created['id']}/pickup", headers=auth_headers(user))
    assert response.status_code == 403


def test_mark_picked_up_forbidden_for_another_library(
    client, reservation_setup, auth_headers, make_user
):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    outsider = make_user(UserRole.librarian, library_id=None)
    response = client.patch(
        f"/reservations/{created['id']}/pickup", headers=auth_headers(outsider)
    )
    assert response.status_code == 403


def test_mark_picked_up_not_found(client, sysadmin_headers):
    response = client.patch("/reservations/9999/pickup", headers=sysadmin_headers)
    assert response.status_code == 404
