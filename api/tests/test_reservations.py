from datetime import datetime, timedelta, timezone

import pytest

from app.persistence.models import Book, Library, PhysicalBook, Reservation, UserRole


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


def test_mine_returns_own_reservations_regardless_of_role(
    client, reservation_setup, auth_headers, make_user, db_session
):
    """A librarian can reserve at any branch, including one that is not theirs.

    Without `mine`, the role scope would narrow the listing to their own branch and
    hide the reservation from them.
    """
    physical_book, _ = reservation_setup

    other_library = Library(name="Norte", address="Calle 2", state="SF", city="Rosario")
    db_session.add(other_library)
    db_session.commit()

    librarian = make_user(UserRole.librarian, library_id=other_library.id)
    headers = auth_headers(librarian)
    created = _reserve(client, headers, physical_book.id).json()

    # Scoped by role: their branch has no reservations.
    assert client.get("/reservations", headers=headers).json() == []

    response = client.get("/reservations", params={"mine": True}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [r["id"] for r in body] == [created["id"]]
    assert body[0]["user_id"] == librarian.id


def test_mine_does_not_leak_other_peoples_reservations(
    client, reservation_setup, auth_headers, make_user, sysadmin_headers
):
    physical_book, user = reservation_setup
    _reserve(client, auth_headers(user), physical_book.id)

    # A sysadmin sees every reservation, but `mine` narrows it to their own.
    assert len(client.get("/reservations", headers=sysadmin_headers).json()) == 1
    response = client.get("/reservations", params={"mine": True}, headers=sysadmin_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_mine_combines_with_is_open(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    headers = auth_headers(user)
    created = _reserve(client, headers, physical_book.id).json()
    client.post(f"/reservations/{created['id']}/cancel", headers=headers)

    open_only = client.get("/reservations", params={"mine": True, "is_open": True}, headers=headers)
    assert open_only.json() == []

    closed = client.get("/reservations", params={"mine": True, "is_open": False}, headers=headers)
    assert [r["id"] for r in closed.json()] == [created["id"]]


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


def test_create_reservation_rejects_a_past_expiry(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    response = client.post(
        "/reservations",
        json={"physical_book_id": physical_book.id, "expires_at": past},
        headers=auth_headers(user),
    )
    assert response.status_code == 422


def _copy_status(client, physical_book_id) -> str:
    return client.get(f"/physical-books/{physical_book_id}").json()["status"]


def test_cancel_reservation_releases_the_copy(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()
    assert _copy_status(client, physical_book.id) == "reserved"

    response = client.post(f"/reservations/{created['id']}/cancel", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["cancelled_at"] is not None
    assert _copy_status(client, physical_book.id) == "available"


def test_a_cancelled_copy_can_be_reserved_again(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    headers = auth_headers(user)
    created = _reserve(client, headers, physical_book.id).json()
    client.post(f"/reservations/{created['id']}/cancel", headers=headers)

    assert _reserve(client, headers, physical_book.id).status_code == 201


def test_cancel_reservation_twice_conflicts(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    headers = auth_headers(user)
    created = _reserve(client, headers, physical_book.id).json()

    assert client.post(f"/reservations/{created['id']}/cancel", headers=headers).status_code == 200
    assert client.post(f"/reservations/{created['id']}/cancel", headers=headers).status_code == 409


def test_cancel_a_picked_up_reservation_conflicts(
    client, reservation_setup, auth_headers, make_user
):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()
    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    client.patch(f"/reservations/{created['id']}/pickup", headers=auth_headers(librarian))

    response = client.post(f"/reservations/{created['id']}/cancel", headers=auth_headers(user))
    assert response.status_code == 409


def test_cancel_forbidden_for_another_customer(
    client, reservation_setup, auth_headers, make_user
):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    other = make_user(UserRole.customer)
    response = client.post(f"/reservations/{created['id']}/cancel", headers=auth_headers(other))
    assert response.status_code == 403


def test_return_releases_the_copy(client, reservation_setup, auth_headers, make_user):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()
    librarian_headers = auth_headers(make_user(UserRole.librarian, library_id=physical_book.library_id))
    client.patch(f"/reservations/{created['id']}/pickup", headers=librarian_headers)
    assert _copy_status(client, physical_book.id) == "loaned"

    response = client.patch(f"/reservations/{created['id']}/return", headers=librarian_headers)
    assert response.status_code == 200
    assert response.json()["returned_at"] is not None
    assert _copy_status(client, physical_book.id) == "available"


def test_return_before_pickup_conflicts(client, reservation_setup, auth_headers, make_user):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    response = client.patch(f"/reservations/{created['id']}/return", headers=auth_headers(librarian))
    assert response.status_code == 409


def test_return_forbidden_for_the_customer(client, reservation_setup, auth_headers, make_user):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()
    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    client.patch(f"/reservations/{created['id']}/pickup", headers=auth_headers(librarian))

    response = client.patch(f"/reservations/{created['id']}/return", headers=auth_headers(user))
    assert response.status_code == 403


def test_pickup_after_cancelling_conflicts(client, reservation_setup, auth_headers, make_user):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()
    client.post(f"/reservations/{created['id']}/cancel", headers=auth_headers(user))

    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    response = client.patch(f"/reservations/{created['id']}/pickup", headers=auth_headers(librarian))
    assert response.status_code == 409


def test_extend_the_expiry(client, reservation_setup, auth_headers, make_user):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    new_expiry = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    response = client.patch(
        f"/reservations/{created['id']}",
        json={"expires_at": new_expiry},
        headers=auth_headers(librarian),
    )
    assert response.status_code == 200
    assert response.json()["expires_at"] != created["expires_at"]


def test_extend_the_expiry_into_the_past_is_rejected(
    client, reservation_setup, auth_headers, sysadmin_headers
):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.patch(
        f"/reservations/{created['id']}", json={"expires_at": past}, headers=sysadmin_headers
    )
    assert response.status_code == 422


def test_extend_forbidden_for_the_customer(client, reservation_setup, auth_headers):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    new_expiry = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    response = client.patch(
        f"/reservations/{created['id']}", json={"expires_at": new_expiry}, headers=auth_headers(user)
    )
    assert response.status_code == 403


def test_expire_releases_only_the_overdue_ones(
    client, reservation_setup, auth_headers, sysadmin_headers, db_session
):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    # Backdate the expiry past the deadline, the way time would have.
    db_session.expire_all()
    reservation = db_session.get(Reservation, created["id"])
    reservation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    response = client.post("/reservations/expire", headers=sysadmin_headers)
    assert response.status_code == 200
    assert response.json() == {"expired": 1}
    assert _copy_status(client, physical_book.id) == "available"

    detail = client.get(f"/reservations/{created['id']}", headers=sysadmin_headers).json()
    assert detail["cancelled_at"] is not None


def test_expire_is_idempotent(client, reservation_setup, auth_headers, sysadmin_headers, db_session):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()
    db_session.expire_all()
    reservation = db_session.get(Reservation, created["id"])
    reservation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    assert client.post("/reservations/expire", headers=sysadmin_headers).json() == {"expired": 1}
    assert client.post("/reservations/expire", headers=sysadmin_headers).json() == {"expired": 0}


def test_expire_leaves_picked_up_reservations_alone(
    client, reservation_setup, auth_headers, sysadmin_headers, make_user, db_session
):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()
    librarian = make_user(UserRole.librarian, library_id=physical_book.library_id)
    client.patch(f"/reservations/{created['id']}/pickup", headers=auth_headers(librarian))

    db_session.expire_all()
    reservation = db_session.get(Reservation, created["id"])
    reservation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    # An overdue loan is a different problem: expiry only frees copies that
    # were never collected.
    assert client.post("/reservations/expire", headers=sysadmin_headers).json() == {"expired": 0}
    assert _copy_status(client, physical_book.id) == "loaned"


def test_expire_requires_sysadmin(client, make_user, auth_headers):
    assert client.post("/reservations/expire").status_code == 401
    librarian = make_user(UserRole.librarian)
    assert client.post("/reservations/expire", headers=auth_headers(librarian)).status_code == 403


def test_list_filters_open_and_closed(client, reservation_setup, auth_headers, sysadmin_headers):
    physical_book, user = reservation_setup
    created = _reserve(client, auth_headers(user), physical_book.id).json()

    assert len(client.get("/reservations", params={"is_open": True}, headers=sysadmin_headers).json()) == 1
    assert client.get("/reservations", params={"is_open": False}, headers=sysadmin_headers).json() == []

    client.post(f"/reservations/{created['id']}/cancel", headers=auth_headers(user))

    assert client.get("/reservations", params={"is_open": True}, headers=sysadmin_headers).json() == []
    assert len(client.get("/reservations", params={"is_open": False}, headers=sysadmin_headers).json()) == 1
    # Unfiltered still returns the whole history.
    assert len(client.get("/reservations", headers=sysadmin_headers).json()) == 1
