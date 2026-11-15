"""Detección de eventos de reserva (`notifications-roadmap.md` §4 y fase 2).

Los registros **no se arman a mano**: cada test escribe por los repositories (o como escribe el
seed) sobre una tabla propia y le pasa a `detect` lo que el stream de DynamoDB Local devolvió de
verdad. El formato `{"S": …}` / `{"BOOL": …}` y qué atributos trae cada imagen engañan cuando se
inventan.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from app import seed as seeding
from app.streams import StreamReader
from app.notifications import events
from app.notifications.events import Actor, EventType
from app.persistence import keys
from app.persistence.entities import (
    SEED_ORIGIN,
    CancelledBy,
    DeadlineKind,
    PhysicalBookStatus,
    Reservation,
)
from app.persistence.repositories import PhysicalBookRepository, ReservationRepository, _items

from .dynamo_support import temporary_dynamo
from .factories import Factory


def now() -> datetime:
    return datetime.now(timezone.utc)


class Recorder:
    """Engancha el stream de la tabla y devuelve lo que produce cada acción."""

    def __init__(self, table):
        self.reader = StreamReader(table, start="LATEST")

    def capture(self, action) -> list[dict]:
        self.reader.read()  # lo anterior no es de esta acción
        action()
        return self.reader.read()

    def reservation_record(self, action) -> dict:
        """El único registro del ítem principal de la reserva que produjo la acción."""
        records = [r for r in self.capture(action) if events.is_reservation_record(r)]
        assert len(records) == 1, [r["eventName"] for r in records]
        return records[0]


@pytest.fixture(scope="module")
def table():
    """Una tabla con stream para todo el módulo: crear una con 4 GSIs por test es lento, y el
    `Recorder` solo mira lo que pasa después de cada acción."""
    gen = temporary_dynamo(create_table=True)
    table = next(gen)
    try:
        yield table
    finally:
        gen.close()


@pytest.fixture(scope="module")
def make(table) -> Factory:
    """Del módulo, como la tabla: el `Factory` numera emails y nombres, y uno nuevo por test
    repetiría `user1@example.com` sobre la misma tabla."""
    return Factory(table)


@pytest.fixture()
def rec(table) -> Recorder:
    return Recorder(table)


@pytest.fixture()
def repo(table) -> ReservationRepository:
    return ReservationRepository(table)


_counter = iter(range(10**6))


@pytest.fixture()
def copy(make):
    """Un ejemplar nuevo por test, de un libro propio (la tabla es compartida por el módulo)."""
    isbn = f"978{next(_counter):010d}"
    make.book(isbn, f"Libro {isbn}")
    return make.copy(isbn)


def reserve(make, copy, *, expires_in=timedelta(days=3), user=None) -> Reservation:
    return make.reservation(copy, user, expires_in=expires_in)


def only(found: list[events.ReservationEvent]) -> events.ReservationEvent:
    assert len(found) == 1, found
    return found[0]


# -- INSERT -----------------------------------------------------------------


def test_a_new_reservation_is_created(rec, make, copy):
    reservation = None

    def act():
        nonlocal reservation
        reservation = reserve(make, copy)

    event = only(events.detect(rec.reservation_record(act)))

    assert event.type is EventType.created and event.actor is Actor.user
    assert event.occurred_at == reservation.reserved_at
    assert event.reservation == reservation
    assert re.fullmatch(rf"r{reservation.id}\.created\.\d{{8}}T\d{{6}}Z", event.event_id)


def test_a_seeded_insert_is_ignored(rec, table, copy):
    seeded = Reservation(
        id=900_000 + next(_counter),
        user_id=1,
        physical_book_id=copy.id,
        reserved_at=now() - timedelta(days=30),
        expires_at=now() - timedelta(days=20),
        picked_up=True,
        returned_at=now() - timedelta(days=25),
        library_id=copy.library_id,
        isbn=copy.isbn,
        origin=SEED_ORIGIN,
    )
    record = rec.reservation_record(lambda: table.table.put_item(Item=_items.reservation_item(seeded)))
    assert record["eventName"] == "INSERT"
    assert events.detect(record) == []


def test_running_the_whole_seed_produces_no_events(isolated_db):
    """El seed se corre en AWS con el notificador ya desplegado: no puede inundar las bandejas
    con ~190 reservas de historia. Escribe todo con `INSERT`s marcados como sembrados."""
    rec = Recorder(isolated_db)
    records = rec.capture(lambda: seeding.seed(isolated_db))

    reservation_records = [r for r in records if events.is_reservation_record(r)]
    assert len(reservation_records) == 193
    assert {r["eventName"] for r in reservation_records} == {"INSERT"}
    assert [e for r in records for e in events.detect(r)] == []


# -- MODIFY: retiro -----------------------------------------------------------


def test_pickup(rec, repo, make, copy):
    reservation = reserve(make, copy)
    at = now()

    event = only(events.detect(rec.reservation_record(lambda: repo.mark_picked_up(reservation.id, at))))

    assert event.type is EventType.picked_up and event.actor is Actor.library
    assert event.occurred_at == at and event.reservation.picked_up is True


def test_a_pickup_written_without_its_time_falls_back_to_the_record_time(rec, table, make, copy):
    """Un retiro escrito por código anterior a la fase 1 no trae `picked_up_at`. El respaldo es
    la hora del registro, que no cambia si el stream lo reentrega."""
    reservation = reserve(make, copy)
    record = rec.reservation_record(
        lambda: table.table.update_item(
            Key=keys.key(keys.reservation_pk(reservation.id)),
            UpdateExpression="SET picked_up = :yes",
            ExpressionAttributeValues={":yes": True},
        )
    )

    event = only(events.detect(record))

    assert event.type is EventType.picked_up
    assert abs(event.occurred_at - now()) < timedelta(minutes=5)
    assert events.detect(record)[0].event_id == event.event_id


# -- MODIFY: cancelación --------------------------------------------------------


@pytest.mark.parametrize(
    "by, actor", [(CancelledBy.user, Actor.user), (CancelledBy.library, Actor.library)]
)
def test_cancel(rec, repo, make, copy, by, actor):
    reservation = reserve(make, copy)
    at = now()

    event = only(events.detect(rec.reservation_record(lambda: repo.cancel(reservation.id, at, by))))

    assert event.type is EventType.cancelled and event.actor is actor
    assert event.occurred_at == at


def test_losing_a_pending_copy_cancels_the_reservation(rec, table, make, copy):
    reserve(make, copy)

    record = rec.reservation_record(
        lambda: PhysicalBookRepository(table).update_status(copy.id, PhysicalBookStatus.lost)
    )

    event = only(events.detect(record))
    assert event.type is EventType.cancelled and event.actor is Actor.library


def test_losing_a_loaned_copy_is_internal_to_the_library(rec, table, repo, make, copy):
    reservation = reserve(make, copy)
    repo.mark_picked_up(reservation.id)

    record = rec.reservation_record(
        lambda: PhysicalBookRepository(table).update_status(copy.id, PhysicalBookStatus.lost)
    )

    assert events.detect(record) == []


def test_a_close_without_a_reason_reads_as_what_it_meant_before(rec, table, make, copy):
    """Código anterior a la fase 1 cerraba sin `close_reason`: `cancelled_at` era cancelar."""
    reservation = reserve(make, copy)
    record = rec.reservation_record(
        lambda: table.table.update_item(
            Key=keys.key(keys.reservation_pk(reservation.id)),
            UpdateExpression="SET cancelled_at = :at",
            ExpressionAttributeValues={":at": keys.iso(now())},
        )
    )
    assert only(events.detect(record)).type is EventType.cancelled


# -- MODIFY: vencimientos -------------------------------------------------------


def test_expiring_without_a_previous_notice_notifies_the_expired_pickup(rec, repo, make, copy):
    """Un sysadmin corrió «vencer reservas» antes de que pasara el job: el aviso sale igual."""
    reservation = reserve(make, copy, expires_in=timedelta(hours=1))
    when = now() + timedelta(days=1)

    event = only(events.detect(rec.reservation_record(lambda: repo.expire([reservation.id], when))))

    assert event.type is EventType.pickup_expired and event.actor is Actor.system
    assert event.occurred_at == reservation.expires_at  # no la hora a la que se venció


def test_the_pickup_deadline_mark_notifies_the_expired_pickup(rec, repo, make, copy):
    reservation = reserve(make, copy, expires_in=timedelta(hours=1))

    record = rec.reservation_record(
        lambda: repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, reservation.expires_at)
    )

    event = only(events.detect(record))
    assert event.type is EventType.pickup_expired and event.actor is Actor.system
    assert event.occurred_at == reservation.expires_at


def test_expiring_after_the_notice_does_not_repeat_it(rec, repo, make, copy):
    reservation = reserve(make, copy, expires_in=timedelta(hours=1))
    marked = events.detect(
        rec.reservation_record(
            lambda: repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, reservation.expires_at)
        )
    )

    expired = events.detect(
        rec.reservation_record(lambda: repo.expire([reservation.id], now() + timedelta(days=1)))
    )

    assert only(marked).type is EventType.pickup_expired
    assert expired == []


def test_the_return_deadline_mark_notifies_the_overdue_loan(rec, repo, make, copy):
    reservation = reserve(make, copy, expires_in=timedelta(hours=1))
    repo.mark_picked_up(reservation.id)

    record = rec.reservation_record(
        lambda: repo.mark_deadline_notified(reservation.id, DeadlineKind.return_, reservation.expires_at)
    )

    event = only(events.detect(record))
    assert event.type is EventType.return_overdue and event.actor is Actor.system
    assert event.occurred_at == reservation.expires_at


def test_extending_notifies_nothing_even_when_it_removes_the_mark(rec, repo, make, copy):
    reservation = reserve(make, copy, expires_in=timedelta(hours=1))
    plain = rec.reservation_record(lambda: repo.update_expiry(reservation.id, now() + timedelta(days=2)))
    updated = repo.get(reservation.id)
    repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, updated.expires_at)

    removing = rec.reservation_record(
        lambda: repo.update_expiry(reservation.id, now() + timedelta(days=4))
    )

    assert events.detect(plain) == [] and events.detect(removing) == []


def test_a_new_expiry_after_an_extension_is_a_different_event(rec, repo, make, copy):
    reservation = reserve(make, copy, expires_in=timedelta(hours=1))
    first = only(
        events.detect(
            rec.reservation_record(
                lambda: repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, reservation.expires_at)
            )
        )
    )
    new_expiry = now() + timedelta(days=2)
    repo.update_expiry(reservation.id, new_expiry)

    second = only(
        events.detect(
            rec.reservation_record(
                lambda: repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, new_expiry)
            )
        )
    )

    assert first.type is second.type is EventType.pickup_expired
    assert first.event_id != second.event_id


# -- MODIFY: devolución ---------------------------------------------------------


def test_return(rec, repo, make, copy):
    reservation = reserve(make, copy)
    repo.mark_picked_up(reservation.id)
    at = now()

    event = only(events.detect(rec.reservation_record(lambda: repo.mark_returned(reservation.id, at))))

    assert event.type is EventType.returned and event.actor is Actor.library
    assert event.occurred_at == at


# -- lo que no es una reserva, REMOVE y reentregas -----------------------------


def test_only_the_reservation_item_produces_events(rec, make, copy):
    """Reservar escribe el ejemplar, el enlace `COPY#/RES#` y el contador: ninguno es la reserva."""
    records = rec.capture(lambda: reserve(make, copy))

    assert len(records) > 1
    found = [e for r in records for e in events.detect(r)]
    assert [e.type for e in found] == [EventType.created]


def test_a_removed_reservation_produces_nothing(rec, table, make, copy):
    reservation = reserve(make, copy)
    record = rec.reservation_record(
        lambda: table.table.delete_item(Key=keys.key(keys.reservation_pk(reservation.id)))
    )
    assert record["eventName"] == "REMOVE"
    assert events.detect(record) == []


def test_a_redelivered_record_is_the_same_event(rec, repo, make, copy):
    reservation = reserve(make, copy)
    record = rec.reservation_record(lambda: repo.cancel(reservation.id, by=CancelledBy.user))

    assert events.detect(record) == events.detect(record)
    assert events.detect(record)[0].event_id == events.detect(record)[0].event_id


# -- el mensaje que se publica --------------------------------------------------


def test_the_published_message_follows_the_contract(rec, repo, make, copy):
    reservation = reserve(make, copy, expires_in=timedelta(hours=1))
    event = only(
        events.detect(
            rec.reservation_record(
                lambda: repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, reservation.expires_at)
            )
        )
    )

    message = event.to_message()

    stamp = reservation.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert message == {
        "event_id": f"r{reservation.id}.pickup_expired.{reservation.expires_at.strftime('%Y%m%dT%H%M%SZ')}",
        "type": "reservation.pickup_expired",
        "occurred_at": stamp,
        "actor": "system",
        "reservation": {
            "id": reservation.id,
            "user_id": reservation.user_id,
            "library_id": copy.library_id,
            "physical_book_id": copy.id,
            "isbn": copy.isbn,
            "expires_at": stamp,
            "close_reason": None,
        },
    }


def test_a_message_reads_back_as_the_same_event(rec, repo, make, copy):
    reservation = reserve(make, copy)
    event = only(
        events.detect(rec.reservation_record(lambda: repo.cancel(reservation.id, by=CancelledBy.library)))
    )
    message = event.to_message()

    back = events.ReservationEvent.from_message(message)

    assert back.event_id == event.event_id and back.to_message() == message
    assert back.reservation.close_reason is event.reservation.close_reason


def test_a_message_whose_id_does_not_match_its_content_is_rejected(rec, make, copy):
    event = only(events.detect(rec.reservation_record(lambda: reserve(make, copy))))
    message = {**event.to_message(), "event_id": "r1.created.20200101T000000Z"}
    with pytest.raises(ValueError, match="does not match"):
        events.ReservationEvent.from_message(message)


# -- el borrado por TTL de una notificación no leída ----------------------------
# DynamoDB Local no borra por TTL: el `REMOVE` se captura de un borrado real y se le agrega el
# `userIdentity` con el que AWS firma los borrados de TTL (lo único que los distingue).

TTL_IDENTITY = {"type": "Service", "principalId": "dynamodb.amazonaws.com"}


def _notification_removal(rec, table, make, copy, *, read: bool) -> tuple[dict, int]:
    from app.services import notification_service
    from app.persistence.entities import InboxKind
    from app.persistence.repositories import NotificationRepository

    reservation = reserve(make, copy)
    event = events.ReservationEvent(
        type=EventType.created, occurred_at=reservation.reserved_at, actor=Actor.user,
        reservation=reservation,
    )
    notification_service.deliver(table, event)
    repo = NotificationRepository(table)
    [notification], _ = repo.list(InboxKind.library, copy.library_id, now=now(), limit=50)
    if read:
        repo.mark_read(InboxKind.library, copy.library_id, notification.id, by=1, at=now())
    pk = keys.inbox_pk("LIB", copy.library_id)
    sk = keys.notification_sk(reservation.reserved_at, event.event_id)
    [record] = [
        r
        for r in rec.capture(lambda: table.table.delete_item(Key={"PK": pk, "SK": sk}))
        if r["eventName"] == "REMOVE"
    ]
    return record, copy.library_id


def test_a_ttl_removal_of_an_unread_notification_names_its_inbox(rec, table, make, copy):
    from app.persistence.entities import InboxKind

    record, library_id = _notification_removal(rec, table, make, copy, read=False)

    assert events.expired_unread_inbox({**record, "userIdentity": TTL_IDENTITY}) == (
        InboxKind.library,
        library_id,
    )
    assert events.detect({**record, "userIdentity": TTL_IDENTITY}) == []


def test_a_removal_that_is_not_the_ttl_is_not_discounted(rec, table, make, copy):
    record, _ = _notification_removal(rec, table, make, copy, read=False)
    assert events.expired_unread_inbox(record) is None


def test_a_ttl_removal_of_a_read_notification_is_not_discounted(rec, table, make, copy):
    record, _ = _notification_removal(rec, table, make, copy, read=True)
    assert events.expired_unread_inbox({**record, "userIdentity": TTL_IDENTITY}) is None


def test_a_ttl_identity_on_something_else_is_not_a_notification(rec, table, make, copy):
    reservation = reserve(make, copy)
    record = rec.reservation_record(
        lambda: table.table.delete_item(Key=keys.key(keys.reservation_pk(reservation.id)))
    )
    assert events.expired_unread_inbox({**record, "userIdentity": TTL_IDENTITY}) is None
