from datetime import datetime, timedelta, timezone

import pytest

from app.persistence.models import (
    Book,
    Library,
    PhysicalBook,
    PhysicalBookStatus,
    Reservation,
    UserRole,
)

ISBN = "9780307474728"


@pytest.fixture()
def catalog(db_session):
    central = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    norte = Library(name="Norte", address="Calle 2", state="SF", city="Rosario")
    db_session.add_all([central, norte])
    db_session.flush()
    db_session.add(Book(isbn=ISBN, title="Cien años de soledad", language="es"))
    db_session.commit()
    db_session.refresh(central)
    db_session.refresh(norte)
    return central, norte


def test_create_physical_book(client, catalog, sysadmin_headers):
    central, _ = catalog
    response = client.post(
        "/physical-books",
        json={"isbn": ISBN, "library_id": central.id},
        headers=sysadmin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["isbn"] == ISBN
    assert body["library_id"] == central.id
    assert body["status"] == "available"


def test_create_physical_book_requires_staff(client, catalog, make_user, auth_headers):
    central, _ = catalog
    payload = {"isbn": ISBN, "library_id": central.id}

    assert client.post("/physical-books", json=payload).status_code == 401
    response = client.post("/physical-books", json=payload, headers=auth_headers(make_user()))
    assert response.status_code == 403


def test_librarian_can_only_add_copies_to_their_own_library(
    client, catalog, make_user, auth_headers
):
    central, norte = catalog
    headers = auth_headers(make_user(UserRole.librarian, library_id=central.id))

    own = client.post(
        "/physical-books", json={"isbn": ISBN, "library_id": central.id}, headers=headers
    )
    assert own.status_code == 201

    other = client.post(
        "/physical-books", json={"isbn": ISBN, "library_id": norte.id}, headers=headers
    )
    assert other.status_code == 403


def test_create_physical_book_with_unknown_book(client, catalog, sysadmin_headers):
    central, _ = catalog
    # Well-formed ISBN-13, but no such book in the catalog.
    response = client.post(
        "/physical-books",
        json={"isbn": "9788437604572", "library_id": central.id},
        headers=sysadmin_headers,
    )
    assert response.status_code == 404


def test_create_physical_book_with_unknown_library(client, catalog, sysadmin_headers):
    response = client.post(
        "/physical-books", json={"isbn": ISBN, "library_id": 9999}, headers=sysadmin_headers
    )
    assert response.status_code == 404


def test_create_physical_book_rejects_malformed_isbn(client, catalog, sysadmin_headers):
    central, _ = catalog
    response = client.post(
        "/physical-books",
        json={"isbn": "978030747472", "library_id": central.id},
        headers=sysadmin_headers,
    )
    assert response.status_code == 422


def test_list_physical_books_is_public_and_filterable(client, catalog, db_session):
    central, norte = catalog
    db_session.add_all(
        [
            PhysicalBook(isbn=ISBN, library_id=central.id),
            PhysicalBook(isbn=ISBN, library_id=norte.id, status=PhysicalBookStatus.lost),
        ]
    )
    db_session.commit()

    assert len(client.get("/physical-books").json()) == 2
    assert len(client.get("/physical-books", params={"library_id": central.id}).json()) == 1
    assert len(client.get("/physical-books", params={"status": "lost"}).json()) == 1
    assert len(client.get("/physical-books", params={"isbn": ISBN}).json()) == 2
    assert client.get("/physical-books", params={"isbn": "9780000000000"}).json() == []


def test_get_physical_book(client, catalog, db_session):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    response = client.get(f"/physical-books/{copy.id}")
    assert response.status_code == 200
    assert response.json()["id"] == copy.id


def test_get_physical_book_not_found(client):
    assert client.get("/physical-books/9999").status_code == 404


def test_mark_a_copy_as_lost(client, catalog, db_session, sysadmin_headers):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    response = client.patch(
        f"/physical-books/{copy.id}/status", json={"status": "lost"}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "lost"


def test_a_lost_copy_can_go_back_to_available(client, catalog, db_session, sysadmin_headers):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id, status=PhysicalBookStatus.lost)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    response = client.patch(
        f"/physical-books/{copy.id}/status", json={"status": "available"}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "available"


@pytest.mark.parametrize("status", ["reserved", "loaned"])
def test_reservation_statuses_cannot_be_set_by_hand(
    client, catalog, db_session, sysadmin_headers, status
):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    response = client.patch(
        f"/physical-books/{copy.id}/status", json={"status": status}, headers=sysadmin_headers
    )
    assert response.status_code == 409


def test_a_held_copy_cannot_be_sent_back_to_the_shelf(
    client, catalog, db_session, sysadmin_headers
):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id, status=PhysicalBookStatus.reserved)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    # Freeing a held copy is cancel/return's job, not a manual status flip.
    response = client.patch(
        f"/physical-books/{copy.id}/status", json={"status": "available"}, headers=sysadmin_headers
    )
    assert response.status_code == 409


def test_marking_a_reserved_copy_lost_cancels_its_reservation(
    client, catalog, db_session, sysadmin_headers, make_user, auth_headers
):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    customer = make_user()
    created = client.post(
        "/reservations",
        json={
            "physical_book_id": copy.id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
        headers=auth_headers(customer),
    ).json()

    response = client.patch(
        f"/physical-books/{copy.id}/status", json={"status": "lost"}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "lost"

    detail = client.get(f"/reservations/{created['id']}", headers=sysadmin_headers).json()
    assert detail["cancelled_at"] is not None
    assert detail["returned_at"] is None


def test_marking_a_loaned_copy_lost_closes_it_as_returned(
    client, catalog, db_session, sysadmin_headers, make_user, auth_headers
):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    customer = make_user()
    created = client.post(
        "/reservations",
        json={
            "physical_book_id": copy.id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
        headers=auth_headers(customer),
    ).json()
    client.patch(f"/reservations/{created['id']}/pickup", headers=sysadmin_headers)

    response = client.patch(
        f"/physical-books/{copy.id}/status", json={"status": "lost"}, headers=sysadmin_headers
    )
    assert response.status_code == 200

    # The patron had it, so the loan closes as returned even though the copy is gone.
    detail = client.get(f"/reservations/{created['id']}", headers=sysadmin_headers).json()
    assert detail["returned_at"] is not None


def test_update_status_not_found(client, sysadmin_headers):
    response = client.patch(
        "/physical-books/9999/status", json={"status": "lost"}, headers=sysadmin_headers
    )
    assert response.status_code == 404


def test_delete_physical_book(client, catalog, db_session, sysadmin_headers):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id)
    db_session.add(copy)
    db_session.commit()
    db_session.refresh(copy)

    response = client.delete(f"/physical-books/{copy.id}", headers=sysadmin_headers)
    assert response.status_code == 204
    assert client.get(f"/physical-books/{copy.id}").status_code == 404


def test_delete_physical_book_conflicts_with_reservations(
    client, catalog, db_session, sysadmin_headers, make_user
):
    central, _ = catalog
    copy = PhysicalBook(isbn=ISBN, library_id=central.id)
    db_session.add(copy)
    db_session.flush()
    db_session.add(
        Reservation(
            user_id=make_user().id,
            physical_book_id=copy.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
    )
    db_session.commit()
    db_session.refresh(copy)

    response = client.delete(f"/physical-books/{copy.id}", headers=sysadmin_headers)
    assert response.status_code == 409


def test_delete_physical_book_not_found(client, sysadmin_headers):
    assert client.delete("/physical-books/9999", headers=sysadmin_headers).status_code == 404
