"""Los endpoints de notificaciones y su autorización (`notifications-roadmap.md` §6 y fase 4)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.notifications.events import Actor, EventType, ReservationEvent
from app.persistence.entities import UserRole
from app.services import notification_service


@pytest.fixture()
def setup(db, make, make_user):
    """Una sede con su librarian, otra sede con el suyo, y un lector con notificaciones en su
    bandeja y en la de la primera sede."""
    sur, norte = make.library("Sur"), make.library("Norte")
    make.book()
    reader = make_user(UserRole.customer)
    librarian = make_user(UserRole.librarian, library_id=sur.id)
    other_librarian = make_user(UserRole.librarian, library_id=norte.id)

    def notify(library=sur, n=1):
        reservation = make.reservation(make.copy(library=library), reader)
        for i in range(n):
            notification_service.deliver(
                db,
                ReservationEvent(
                    type=EventType.created,
                    occurred_at=reservation.reserved_at + timedelta(seconds=i),
                    actor=Actor.user,
                    reservation=reservation,
                ),
            )
        return reservation

    return sur, norte, reader, librarian, other_librarian, notify


def get(client, headers, **params):
    return client.get("/notifications", params=params, headers=headers)


# -- autenticación y autorización ------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/notifications"),
        ("get", "/notifications/unread-count"),
        ("patch", "/notifications/me/abc/read"),
        ("post", "/notifications/me/read-all"),
    ],
)
def test_every_endpoint_requires_a_token(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_a_customer_has_no_library_inbox(client, setup, auth_headers):
    _, _, reader, *_ = setup
    headers = auth_headers(reader)

    assert get(client, headers, scope="library").status_code == 403
    assert client.post("/notifications/library/read-all", headers=headers).status_code == 403
    assert client.get("/notifications/unread-count", headers=headers).json()["library"] is None


def test_a_sysadmin_has_no_library_inbox(client, setup, sysadmin_headers):
    assert get(client, sysadmin_headers, scope="library").status_code == 403
    assert client.get("/notifications/unread-count", headers=sysadmin_headers).json() == {
        "me": 0,
        "library": None,
    }


def test_a_librarian_without_a_library_has_no_library_inbox(client, make_user, auth_headers):
    headers = auth_headers(make_user(UserRole.librarian))
    assert get(client, headers, scope="library").status_code == 403
    assert client.get("/notifications/unread-count", headers=headers).json()["library"] is None


def test_a_librarian_only_sees_the_inbox_of_their_own_library(client, setup, auth_headers):
    sur, norte, reader, librarian, other_librarian, notify = setup
    mine = notify(sur)
    notify(norte)

    sur_items = get(client, auth_headers(librarian), scope="library").json()["items"]
    norte_items = get(client, auth_headers(other_librarian), scope="library").json()["items"]

    assert [n["reservation_id"] for n in sur_items] == [mine.id]
    assert all(n["library_id"] == norte.id for n in norte_items) and len(norte_items) == 1
    # Su bandeja personal es otra, y está vacía: las del lector no son suyas.
    assert get(client, auth_headers(librarian)).json()["items"] == []


def test_a_notification_of_another_inbox_cannot_be_marked(client, setup, auth_headers):
    sur, norte, reader, librarian, other_librarian, notify = setup
    notify(sur)
    [sur_notification] = get(client, auth_headers(librarian), scope="library").json()["items"]

    response = client.patch(
        f"/notifications/library/{sur_notification['id']}/read",
        headers=auth_headers(other_librarian),
    )

    assert response.status_code == 404
    counts = client.get("/notifications/unread-count", headers=auth_headers(librarian)).json()
    assert counts["library"] == 1


# -- listar y contar --------------------------------------------------------------


def test_the_reader_lists_their_inbox_and_counts(client, setup, auth_headers):
    sur, _, reader, librarian, _, notify = setup
    reservation = notify(sur)
    headers = auth_headers(reader)

    body = get(client, headers).json()

    [item] = body["items"]
    assert body["next_cursor"] is None
    assert item["type"] == "reservation.created" and item["title"] == "Reserva confirmada"
    assert item["reservation_id"] == reservation.id and item["library_id"] == sur.id
    assert item["read_at"] is None and item["read_by"] is None and item["id"]
    assert client.get("/notifications/unread-count", headers=headers).json() == {"me": 1, "library": None}
    assert client.get("/notifications/unread-count", headers=auth_headers(librarian)).json() == {
        "me": 0,
        "library": 1,
    }


def test_pagination_with_the_cursor(client, setup, auth_headers):
    sur, _, reader, _, _, notify = setup
    notify(sur, n=3)
    headers = auth_headers(reader)

    first = get(client, headers, limit=2).json()
    second = get(client, headers, limit=2, cursor=first["next_cursor"]).json()

    assert len(first["items"]) == 2 and first["next_cursor"]
    assert len(second["items"]) == 1
    ids = [n["id"] for n in first["items"] + second["items"]]
    assert len(set(ids)) == 3
    stamps = [n["created_at"] for n in first["items"] + second["items"]]
    assert stamps == sorted(stamps, reverse=True)


@pytest.mark.parametrize("params", [{"limit": 51}, {"limit": 0}, {"cursor": "%%%"}, {"cursor": "UkVTIzE"}, {"scope": "all"}])
def test_invalid_listing_parameters_are_a_422(client, setup, auth_headers, params):
    _, _, reader, *_ = setup
    assert get(client, auth_headers(reader), **params).status_code == 422


# -- marcar como leídas -------------------------------------------------------------


def test_marking_one_as_read_lowers_the_counter_once(client, setup, auth_headers):
    sur, _, reader, librarian, _, notify = setup
    notify(sur)
    headers = auth_headers(librarian)
    [item] = get(client, headers, scope="library").json()["items"]

    first = client.patch(f"/notifications/library/{item['id']}/read", headers=headers)
    second = client.patch(f"/notifications/library/{item['id']}/read", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["read_at"] is not None and first.json()["read_by"] == librarian.id
    assert second.json() == first.json()
    assert client.get("/notifications/unread-count", headers=headers).json()["library"] == 0
    # La del lector sigue sin leer: son dos notificaciones distintas.
    assert client.get("/notifications/unread-count", headers=auth_headers(reader)).json()["me"] == 1


def test_marking_a_missing_or_malformed_notification(client, setup, auth_headers):
    _, _, reader, *_ = setup
    headers = auth_headers(reader)
    missing = "Tk9USUYjMjAyMC0wMS0wMVQwMDowMDowMC4wMDAwMDBaI3IxLmNyZWF0ZWQ"  # NOTIF#2020-...
    assert client.patch(f"/notifications/me/{missing}/read", headers=headers).status_code == 404
    assert client.patch("/notifications/me/UkVTIzE/read", headers=headers).status_code == 422
    assert client.patch("/notifications/other/x/read", headers=headers).status_code == 422


def test_marking_all_as_read(client, setup, auth_headers):
    sur, _, reader, librarian, _, notify = setup
    notify(sur, n=3)
    headers = auth_headers(reader)

    assert client.post("/notifications/me/read-all", headers=headers).json() == {"marked": 3}
    assert client.post("/notifications/me/read-all", headers=headers).json() == {"marked": 0}

    assert client.get("/notifications/unread-count", headers=headers).json()["me"] == 0
    assert all(n["read_at"] for n in get(client, headers).json()["items"])
    # La bandeja de la sede no se tocó.
    assert client.get("/notifications/unread-count", headers=auth_headers(librarian)).json()["library"] == 3


def test_a_librarian_moved_to_another_library_sees_the_new_inbox(client, db, setup, auth_headers):
    from app.persistence.repositories import UserRepository

    sur, norte, _, librarian, _, notify = setup
    notify(sur)
    headers = auth_headers(librarian)
    assert len(get(client, headers, scope="library").json()["items"]) == 1

    UserRepository(db).update(librarian.id, library_id=norte.id)

    assert get(client, headers, scope="library").json()["items"] == []
