"""Carreras por HTTP: lo que Postgres cubría con su transacción y DynamoDB cubre con
escrituras condicionales (ROADMAP §4.2, §4.4). A nivel repository están en
`tests/repositories/`; acá se prueba que el contrato HTTP se mantiene."""

import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app

from .conftest import PASSWORD

THREADS = 6


def _race(calls):
    """Lanza todas las llamadas a la vez y devuelve sus respuestas."""
    barrier = threading.Barrier(len(calls))
    responses = [None] * len(calls)

    def run(i, call):
        barrier.wait()
        responses[i] = call()

    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return responses


@pytest.fixture()
def http(client):
    """Un cliente por thread: `TestClient` no es seguro de compartir entre threads."""
    return lambda: TestClient(app)


def test_simultaneous_reservations_of_one_copy_give_one_201_and_the_rest_409(
    client, http, make, make_user, auth_headers
):
    make.book()
    copy = make.copy()
    headers = [auth_headers(make_user()) for _ in range(THREADS)]
    body = {
        "physical_book_id": copy.id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
    }

    responses = _race(
        [lambda h=h: http().post("/reservations", json=body, headers=h) for h in headers]
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [201] + [409] * (THREADS - 1)
    assert client.get(f"/physical-books/{copy.id}").json()["status"] == "reserved"
    assert len(client.get("/physical-books", params={"status": "available"}).json()) == 0


def test_simultaneous_signups_with_the_same_email_give_one_201_and_the_rest_409(client, http):
    payload = {"email": "carrera@example.com", "password": PASSWORD, "name": "Carrera"}

    responses = _race([lambda: http().post("/users", json=payload) for _ in range(THREADS)])

    assert sorted(r.status_code for r in responses) == [201] + [409] * (THREADS - 1)
    # Y quedó exactamente una cuenta, con la que se puede entrar.
    login = client.post("/auth/login", json={"email": payload["email"], "password": PASSWORD})
    assert login.status_code == 200


def test_ids_never_repeat_under_concurrent_creates(client, http, sysadmin_headers):
    responses = _race(
        [
            lambda i=i: http().post("/authors", json={"name": f"Autor {i}"}, headers=sysadmin_headers)
            for i in range(THREADS * 2)
        ]
    )

    assert all(r.status_code == 201 for r in responses)
    ids = sorted(r.json()["id"] for r in responses)
    assert len(set(ids)) == len(ids) == THREADS * 2
    assert len(client.get("/authors").json()) == THREADS * 2


def test_ids_continue_after_existing_ones(client, make, sysadmin_headers):
    """El contador no reinicia ni pisa lo que ya está: el siguiente alta es el N+1."""
    existing = [make.author(f"Previo {i}") for i in range(3)]

    created = client.post("/authors", json={"name": "Nuevo"}, headers=sysadmin_headers).json()

    assert created["id"] == max(a.id for a in existing) + 1
    assert client.get(f"/authors/{existing[0].id}").json()["name"] == "Previo 0"


def test_a_reservation_closed_over_http_leaves_the_expiry_index(
    client, make, make_user, auth_headers, sysadmin_headers, db
):
    from app.persistence.repositories import ReservationRepository

    make.book()
    copy = make.copy()
    user = make_user()
    created = client.post(
        "/reservations",
        json={
            "physical_book_id": copy.id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=auth_headers(user),
    ).json()
    far_future = datetime.now(timezone.utc) + timedelta(days=30)
    assert [r.id for r in ReservationRepository(db).list_expired(far_future)] == [created["id"]]

    client.post(f"/reservations/{created['id']}/cancel", headers=auth_headers(user))

    assert ReservationRepository(db).list_expired(far_future) == []
    assert client.post("/reservations/expire", headers=sysadmin_headers).json() == {"expired": 0}


def test_expire_handles_more_reservations_than_a_transaction_holds(make, db):
    from app.persistence.entities import PhysicalBookStatus
    from app.persistence.repositories import PhysicalBookRepository
    from app.services import reservation_service

    make.book()
    library = make.library()
    user = make.user()
    for _ in range(105):
        make.reservation(make.copy(library=library), user, expires_in=timedelta(hours=1))

    later = datetime.now(timezone.utc) + timedelta(days=1)  # pasa el tiempo
    assert reservation_service.expire_reservations(db, later) == 105

    assert reservation_service.expire_reservations(db, later) == 0  # idempotente
    available = PhysicalBookRepository(db).list_all(status=PhysicalBookStatus.available)
    assert len(available) == 105
