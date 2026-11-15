"""El pipeline de notificaciones (`notifications-roadmap.md` §9 y fase 5): stream → notificador
→ bus → inbox-writer → bandeja, y el job de vencimientos.

Los registros del stream salen de DynamoDB Local de verdad (como en `test_notification_events`),
y el bus es el `inline`, que arma el mismo evento que SNS le pasa a Lambda. Lo único que no se
ejercita es el `Publish` real a SNS, que se prueba contra un cliente falso.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import Settings, settings

from app.notifications import inbox_writer, notifier
from app.notifications.bus import InlineBus, NullBus, SnsBus, get_bus, message_body, sns_lambda_event
from app.notifications.events import EventType, detect
from app.persistence import keys
from app.persistence.entities import CancelledBy, DeadlineKind, InboxKind
from app.persistence.repositories import NotificationRepository, ReservationRepository
from app.services import notification_service
from app.streams import StreamReader

from .factories import Factory

USER, LIB = InboxKind.user, InboxKind.library
SNS_EVENT = Path(__file__).parent / "fixtures" / "sns_lambda_event.json"


def now() -> datetime:
    return datetime.now(timezone.utc)


class Pipeline:
    """Una tabla con stream y el notificador enganchado a él, con el bus inline."""

    def __init__(self, db):
        self.db = db
        self.reader = StreamReader(db, start="LATEST")
        self.bus = InlineBus(db)

    def records(self, action) -> list[dict]:
        self.reader.read()  # lo anterior no es de esta acción
        action()
        return self.reader.read()

    def run(self, action) -> dict[str, int]:
        return notifier.process(self.db, self.records(action), bus=self.bus)

    def inbox(self, kind: InboxKind, owner: int):
        return NotificationRepository(self.db).list(kind, owner, now=now())[0]

    def unread(self, kind: InboxKind, owner: int) -> int:
        return NotificationRepository(self.db).unread_count(kind, owner)


@pytest.fixture()
def pipe(isolated_db) -> Pipeline:
    return Pipeline(isolated_db)


@pytest.fixture()
def world(isolated_db):
    make = Factory(isolated_db)
    library = make.library("Biblioteca Sur")
    make.book(title="Rayuela")
    reader = make.user(name="Ana Pérez")
    return make, library, reader


def reserve(make, library, reader, *, expires_in=timedelta(days=3)):
    return make.reservation(make.copy(library=library), reader, expires_in=expires_in)


# -- de punta a punta ---------------------------------------------------------


def test_a_reservation_reaches_both_inboxes(pipe, world):
    make, library, reader = world
    result = pipe.run(lambda: reserve(make, library, reader))

    assert result == {"published": 1, "decremented": 0}
    [mine] = pipe.inbox(USER, reader.id)
    [theirs] = pipe.inbox(LIB, library.id)
    assert mine.type == theirs.type == EventType.created.value
    assert mine.title == "Reserva confirmada" and "«Rayuela»" in mine.body
    assert theirs.title == "Nueva reserva" and theirs.body.startswith("Ana Pérez reservó")
    assert pipe.unread(USER, reader.id) == pipe.unread(LIB, library.id) == 1


def test_a_redelivered_batch_does_not_duplicate(pipe, world):
    """Lambda reintenta lotes enteros y SNS entrega al menos una vez: la bandeja descarta."""
    make, library, reader = world
    records = pipe.records(lambda: reserve(make, library, reader))

    notifier.process(pipe.db, records, bus=pipe.bus)
    notifier.process(pipe.db, records, bus=pipe.bus)

    assert len(pipe.inbox(USER, reader.id)) == len(pipe.inbox(LIB, library.id)) == 1
    assert pipe.unread(USER, reader.id) == 1


def test_the_whole_lifecycle_notifies_each_step(pipe, world):
    make, library, reader = world
    repo = ReservationRepository(pipe.db)
    reservation = None

    def create():
        nonlocal reservation
        reservation = reserve(make, library, reader)

    pipe.run(create)
    pipe.run(lambda: repo.mark_picked_up(reservation.id))
    pipe.run(lambda: repo.mark_returned(reservation.id))

    types = [n.type for n in pipe.inbox(USER, reader.id)]
    assert types == [EventType.returned.value, EventType.picked_up.value, EventType.created.value]
    assert pipe.unread(LIB, library.id) == 3


def test_a_cancellation_by_the_reader(pipe, world):
    make, library, reader = world
    reservation = reserve(make, library, reader)
    repo = ReservationRepository(pipe.db)

    pipe.run(lambda: repo.cancel(reservation.id, by=CancelledBy.user))

    [mine] = pipe.inbox(USER, reader.id)
    assert mine.type == EventType.cancelled.value and mine.body.startswith("Cancelaste")


def test_writes_that_are_not_reservations_publish_nothing(pipe, world):
    make, library, _ = world
    assert pipe.run(lambda: make.copy(library=library)) == {"published": 0, "decremented": 0}


def test_the_ttl_removal_of_an_unread_notification_decrements_the_counter(pipe, world):
    make, library, reader = world
    pipe.run(lambda: reserve(make, library, reader))
    [mine] = pipe.inbox(USER, reader.id)
    pk = keys.inbox_pk("USER", reader.id)
    sk = next(
        i["SK"]
        for i in pipe.db.table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :p)",
            ExpressionAttributeValues={":pk": pk, ":p": keys.NOTIFICATION_PREFIX},
        )["Items"]
    )

    # DynamoDB Local no borra por TTL: se borra a mano y se le pone al registro la identidad
    # con la que DynamoDB firma sus propios borrados.
    [record] = [
        r for r in pipe.records(lambda: pipe.db.table.delete_item(Key={"PK": pk, "SK": sk}))
        if r["eventName"] == "REMOVE"
    ]
    record["userIdentity"] = {"type": "Service", "principalId": "dynamodb.amazonaws.com"}

    assert notifier.process(pipe.db, [record], bus=pipe.bus) == {"published": 0, "decremented": 1}
    assert pipe.unread(USER, reader.id) == 0
    assert mine.read_at is None


# -- el job de vencimientos ---------------------------------------------------


@pytest.fixture()
def booked(make):
    """El libro por defecto del `Factory`, para que `make.reservation()` pueda crear ejemplares."""
    make.book()
    return make


def test_an_expired_pickup_is_noticed_through_the_stream(pipe, world):
    make, library, reader = world
    reserve(make, library, reader, expires_in=timedelta(hours=1))
    later = now() + timedelta(hours=2)

    result = pipe.run(lambda: notification_service.scan_deadlines(pipe.db, now=later))

    assert result["published"] == 1
    [mine] = pipe.inbox(USER, reader.id)[:1]
    assert mine.type == EventType.pickup_expired.value
    assert pipe.inbox(LIB, library.id)[0].title == "Retiro vencido"


def test_scan_marks_each_deadline_once(db, booked):
    repo = ReservationRepository(db)
    pending = booked.reservation(expires_in=timedelta(hours=1))
    loaned = booked.reservation(expires_in=timedelta(hours=1))
    repo.mark_picked_up(loaned.id)
    on_time = booked.reservation(expires_in=timedelta(days=3))
    closed = booked.reservation(expires_in=timedelta(hours=1))
    repo.cancel(closed.id, by=CancelledBy.user)
    later = now() + timedelta(hours=2)

    assert notification_service.scan_deadlines(db, now=later) == 2
    assert notification_service.scan_deadlines(db, now=later) == 0

    assert repo.get(pending.id).pickup_deadline_notified_at == later
    assert repo.get(loaned.id).return_deadline_notified_at == later
    assert repo.get(loaned.id).pickup_deadline_notified_at is None
    assert repo.get(on_time.id).pickup_deadline_notified_at is None
    assert repo.get(closed.id).pickup_deadline_notified_at is None


def test_an_extension_lets_the_next_expiry_be_noticed_again(db, booked):
    repo = ReservationRepository(db)
    reservation = booked.reservation(expires_in=timedelta(hours=1))
    assert notification_service.scan_deadlines(db, now=now() + timedelta(hours=2)) == 1

    repo.update_expiry(reservation.id, now() + timedelta(hours=3))

    assert notification_service.scan_deadlines(db, now=now() + timedelta(hours=2)) == 0
    assert notification_service.scan_deadlines(db, now=now() + timedelta(hours=4)) == 1


def test_scan_skips_a_reservation_that_changed_after_the_listing(db, booked, monkeypatch):
    """La condición de la marca es lo que decide: si la extienden entre el listado y la marca,
    no se avisa un vencimiento que ya no es."""
    repo = ReservationRepository(db)
    reservation = booked.reservation(expires_in=timedelta(hours=1))
    listed = repo.list_past_due(now() + timedelta(hours=2))
    repo.update_expiry(reservation.id, now() + timedelta(days=1))
    monkeypatch.setattr(ReservationRepository, "list_past_due", lambda self, at: listed)

    assert notification_service.scan_deadlines(db, now=now() + timedelta(hours=2)) == 0
    assert repo.get(reservation.id).pickup_deadline_notified_at is None


# -- el inbox-writer y el formato de SNS --------------------------------------


def _captured_event(pipe, world):
    make, library, reader = world
    [record] = [
        r for r in pipe.records(lambda: reserve(make, library, reader)) if detect(r)
    ]
    return detect(record)[0]


def test_the_inbox_writer_reads_a_real_sns_event(pipe, world):
    """El evento de ejemplo de AWS (SNS → Lambda), con nuestro mensaje adentro."""
    event = _captured_event(pipe, world)
    sns_event = json.loads(SNS_EVENT.read_text())
    sns_event["Records"][0]["Sns"]["Message"] = message_body(event)

    assert inbox_writer.process(pipe.db, sns_event) == {"delivered": 1, "duplicates": 0}
    assert inbox_writer.process(pipe.db, sns_event) == {"delivered": 0, "duplicates": 1}


def _shape(value):
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(v) for v in value]
    return type(value).__name__ if value is not None else "str"


def test_the_inline_bus_imitates_the_sns_event_shape(pipe, world):
    """Si el bus inline divergiera del formato real, en local andaría y en AWS no."""
    event = _captured_event(pipe, world)
    real = json.loads(SNS_EVENT.read_text())["Records"][0]
    ours = sns_lambda_event(event)["Records"][0]

    assert set(ours) == set(real)
    assert set(ours["Sns"]) == set(real["Sns"])
    assert _shape({k: v for k, v in ours["Sns"].items() if k != "MessageAttributes"}) == _shape(
        {k: v for k, v in real["Sns"].items() if k != "MessageAttributes"}
    )
    assert ours["Sns"]["MessageAttributes"] == {
        "event_type": {"Type": "String", "Value": "reservation.created"}
    }
    assert json.loads(ours["Sns"]["Message"]) == event.to_message()


# -- los buses ----------------------------------------------------------------


class FakeSns:
    def __init__(self):
        self.published: list[dict] = []

    def publish(self, **kwargs):
        self.published.append(kwargs)
        return {"MessageId": "1"}


def test_the_sns_bus_publishes_the_contract(pipe, world):
    event = _captured_event(pipe, world)
    client = FakeSns()

    SnsBus("arn:aws:sns:us-east-1:1:topic", client).publish(event)

    [call] = client.published
    assert call["TopicArn"] == "arn:aws:sns:us-east-1:1:topic"
    assert json.loads(call["Message"]) == event.to_message()
    assert call["MessageAttributes"] == {
        "event_type": {"DataType": "String", "StringValue": "reservation.created"}
    }


def test_the_null_bus_delivers_nothing(pipe, world):
    make, library, reader = world
    records = pipe.records(lambda: reserve(make, library, reader))

    assert notifier.process(pipe.db, records, bus=NullBus())["published"] == 1
    assert pipe.inbox(USER, reader.id) == []


@pytest.mark.parametrize(
    "value, expected", [("", NullBus), ("inline", InlineBus), ("sns", SnsBus)]
)
def test_get_bus_follows_the_setting(db, monkeypatch, value, expected):
    monkeypatch.setattr(settings, "notifications_bus", value)
    monkeypatch.setattr(settings, "notifications_topic_arn", "arn:aws:sns:us-east-1:1:topic")
    assert isinstance(get_bus(db), expected)


def test_the_sns_bus_requires_a_topic():
    with pytest.raises(ValueError, match="NOTIFICATIONS_TOPIC_ARN"):
        Settings(_env_file=None, notifications_bus="sns", notifications_topic_arn="")
