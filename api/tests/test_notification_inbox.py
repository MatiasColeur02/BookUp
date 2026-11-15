"""La bandeja: entrega, contador de no leídas, lectura y paginación (`notifications-roadmap.md`
§5.2, §5.3 y fase 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.notifications.events import Actor, EventType, ReservationEvent
from app.persistence import keys
from app.persistence.entities import CancelledBy, InboxKind, Reservation, UserRole
from app.persistence.errors import InvalidReferenceError
from app.persistence.repositories import (
    NotificationRepository,
    ReservationRepository,
    UserRepository,
)
from app.services import notification_service

USER, LIB = InboxKind.user, InboxKind.library


def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def world(make):
    library = make.library("Biblioteca Sur")
    make.book(title="Rayuela")
    reader = make.user(name="Ana Pérez")
    librarian = make.user(role=UserRole.librarian, library_id=library.id)
    return library, reader, librarian


def event_for(reservation: Reservation, type_=EventType.created, *, at=None, actor=Actor.user):
    return ReservationEvent(
        type=type_, occurred_at=at or reservation.reserved_at, actor=actor, reservation=reservation
    )


@pytest.fixture()
def reserve(make, world):
    library, reader, _ = world

    def _reserve(user=None):
        return make.reservation(make.copy(library=library), user or reader)

    return _reserve


@pytest.fixture()
def repo(db):
    return NotificationRepository(db)


def inbox(repo, kind, owner_id, **kw):
    found, _ = repo.list(kind, owner_id, now=now(), limit=50, **kw)
    return found


# -- entrega ---------------------------------------------------------------------


def test_delivering_writes_one_notification_per_inbox_with_its_text(db, repo, world, reserve):
    library, reader, _ = world
    reservation = reserve()

    assert notification_service.deliver(db, event_for(reservation)) is True

    [mine] = inbox(repo, USER, reader.id)
    [theirs] = inbox(repo, LIB, library.id)
    assert mine.type == theirs.type == "reservation.created"
    assert mine.title == "Reserva confirmada"
    assert mine.body.startswith("Reservaste «Rayuela» en Biblioteca Sur.")
    assert theirs.title == "Nueva reserva"
    assert theirs.body.startswith(f"Ana Pérez reservó «Rayuela» (ejemplar #{reservation.physical_book_id}).")
    for n in (mine, theirs):
        assert n.reservation_id == reservation.id and n.library_id == library.id
        assert n.created_at == reservation.reserved_at and n.read_at is None and n.id
    assert repo.unread_count(USER, reader.id) == 1
    assert repo.unread_count(LIB, library.id) == 1


def test_delivering_the_same_event_twice_writes_it_once(db, repo, world, reserve):
    library, reader, _ = world
    event = event_for(reserve())

    assert notification_service.deliver(db, event) is True
    assert notification_service.deliver(db, event) is False

    assert len(inbox(repo, USER, reader.id)) == 1 and len(inbox(repo, LIB, library.id)) == 1
    assert repo.unread_count(USER, reader.id) == 1
    assert repo.unread_count(LIB, library.id) == 1


def test_the_notification_expires_after_the_retention(db, world, reserve):
    reservation = reserve()
    notification_service.deliver(db, event_for(reservation), retention_days=90)

    item = db.table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :p)",
        ExpressionAttributeValues={":pk": f"INBOX#USER#{reservation.user_id}", ":p": "NOTIF#"},
    )["Items"][0]
    expected = reservation.reserved_at + timedelta(days=90)
    assert int(item["ttl_epoch"]) == int(expected.timestamp())
    assert not any(k.startswith("GSI") for k in item)  # no entra en ningún índice


def test_a_deleted_reader_does_not_break_the_delivery_to_the_library(db, repo, world, reserve):
    library, reader, _ = world
    reservation = reserve()
    UserRepository(db).delete(UserRepository(db).get(reader.id))

    assert notification_service.deliver(db, event_for(reservation)) is True

    [theirs] = inbox(repo, LIB, library.id)
    assert theirs.body.startswith("Un lector reservó «Rayuela»")
    assert inbox(repo, USER, reader.id) == [] and repo.unread_count(USER, reader.id) == 0
    assert repo.unread_count(LIB, library.id) == 1


def test_a_reader_deleted_between_reading_and_writing_still_reaches_the_library(
    db, repo, world, reserve, monkeypatch
):
    library, reader, _ = world
    reservation = reserve()
    stale = UserRepository(db).get(reader.id)
    UserRepository(db).delete(stale)
    monkeypatch.setattr(UserRepository, "get", lambda self, user_id: stale)  # la lectura vieja

    assert notification_service.deliver(db, event_for(reservation)) is True

    assert len(inbox(repo, LIB, library.id)) == 1
    assert inbox(repo, USER, reader.id) == [] and repo.unread_count(USER, reader.id) == 0


def test_the_cancellation_text_depends_on_who_cancelled_and_why(db, repo, world, reserve):
    library, reader, _ = world
    by_reader = ReservationRepository(db).cancel(reserve().id, by=CancelledBy.user)
    by_library = ReservationRepository(db).cancel(reserve().id, by=CancelledBy.library)
    notification_service.deliver(db, event_for(by_reader, EventType.cancelled, at=by_reader.cancelled_at))
    notification_service.deliver(
        db, event_for(by_library, EventType.cancelled, at=by_library.cancelled_at, actor=Actor.library)
    )

    bodies = [n.body for n in inbox(repo, USER, reader.id)]
    assert bodies == ["Biblioteca Sur canceló tu reserva de «Rayuela».", "Cancelaste tu reserva de «Rayuela»."]


# -- leer una ------------------------------------------------------------------


def test_marking_one_as_read_twice_counts_once(db, repo, world, reserve):
    library, reader, librarian = world
    notification_service.deliver(db, event_for(reserve()))
    [notification] = inbox(repo, LIB, library.id)
    at = now()

    first = repo.mark_read(LIB, library.id, notification.id, by=librarian.id, at=at)
    second = repo.mark_read(LIB, library.id, notification.id, by=reader.id, at=now())

    assert first.read_at == at and first.read_by == librarian.id
    assert second == first  # no la vuelve a marcar ni cambia quién la leyó
    assert repo.unread_count(LIB, library.id) == 0
    assert repo.unread_count(USER, reader.id) == 1  # la del lector es otra


def test_marking_a_missing_notification(db, repo, world, reserve):
    library, reader, _ = world
    notification_service.deliver(db, event_for(reserve()))
    [mine] = inbox(repo, USER, reader.id)

    # El id de una notificación de otra bandeja no lee ni marca nada en ésta.
    assert repo.mark_read(LIB, library.id + 1000, mine.id, by=reader.id, at=now()) is None
    assert repo.get(LIB, library.id + 1000, mine.id) is None
    assert repo.unread_count(LIB, library.id + 1000) == 0
    assert repo.unread_count(USER, reader.id) == 1


@pytest.mark.parametrize("bad", ["", "%%%", "bm90LWEtbm90aWY", "UkVTIzE"])  # "not-a-notif", "RES#1"
def test_a_malformed_id_is_rejected(repo, bad):
    with pytest.raises(InvalidReferenceError):
        repo.mark_read(USER, 1, bad, by=1, at=now())
    with pytest.raises(InvalidReferenceError):
        repo.get(USER, 1, bad)


# -- leer todas ------------------------------------------------------------------


def test_marking_all_as_read_leaves_the_counter_at_zero(db, repo, world, reserve):
    library, reader, librarian = world
    for _ in range(3):
        notification_service.deliver(db, event_for(reserve()))
    [first, *_] = inbox(repo, LIB, library.id)
    repo.mark_read(LIB, library.id, first.id, by=librarian.id, at=now())

    assert repo.mark_all_read(LIB, library.id, by=librarian.id, at=now()) == 2

    assert repo.unread_count(LIB, library.id) == 0
    assert all(n.read_at is not None for n in inbox(repo, LIB, library.id))
    assert repo.unread_count(USER, reader.id) == 3  # la otra bandeja no se toca
    assert repo.mark_all_read(LIB, library.id, by=librarian.id, at=now()) == 0


def test_marking_all_crosses_the_transaction_limit(db, repo, world, reserve, make):
    library, reader, librarian = world
    reservation = reserve()
    for i in range(120):  # el mismo evento con distinto instante: 120 notificaciones distintas
        notification_service.deliver(
            db, event_for(reservation, at=reservation.reserved_at + timedelta(seconds=i))
        )
    assert repo.unread_count(LIB, library.id) == 120

    assert repo.mark_all_read(LIB, library.id, by=librarian.id, at=now()) == 120

    assert repo.unread_count(LIB, library.id) == 0


def test_marking_all_corrects_a_drifted_counter(db, repo, world):
    library, _, librarian = world
    pk = keys.inbox_pk("LIB", library.id)
    db.table.put_item(Item={"PK": pk, "SK": keys.UNREAD, "unread": 7})
    assert repo.unread_count(LIB, library.id) == 7

    assert repo.mark_all_read(LIB, library.id, by=librarian.id, at=now()) == 0

    assert repo.unread_count(LIB, library.id) == 0


def test_a_negative_counter_reads_as_zero(db, repo, world):
    library, _, _ = world
    db.table.put_item(Item={"PK": keys.inbox_pk("LIB", library.id), "SK": keys.UNREAD, "unread": -2})
    assert repo.unread_count(LIB, library.id) == 0


def test_decrementing_for_an_unread_removed_by_ttl(db, repo, world, reserve):
    library, reader, _ = world
    notification_service.deliver(db, event_for(reserve()))

    repo.decrement_unread(LIB, library.id)

    assert repo.unread_count(LIB, library.id) == 0
    assert repo.unread_count(USER, reader.id) == 1


# -- listado ---------------------------------------------------------------------


def test_the_inbox_lists_newest_first_and_paginates(db, repo, world, reserve):
    library, _, _ = world
    reservation = reserve()
    base = reservation.reserved_at
    for i in range(5):
        notification_service.deliver(db, event_for(reservation, at=base + timedelta(minutes=i)))

    page1, cursor = repo.list(LIB, library.id, now=now(), limit=2)
    page2, cursor2 = repo.list(LIB, library.id, now=now(), limit=2, cursor=cursor)
    page3, cursor3 = repo.list(LIB, library.id, now=now(), limit=2, cursor=cursor2)

    stamps = [n.created_at for n in page1 + page2 + page3]
    assert stamps == [base + timedelta(minutes=i) for i in (4, 3, 2, 1, 0)]
    assert cursor and cursor2
    if cursor3 is not None:  # DynamoDB puede devolver una última página vacía
        assert repo.list(LIB, library.id, now=now(), limit=2, cursor=cursor3) == ([], None)


def test_the_listing_hides_what_the_ttl_has_not_deleted_yet(db, repo, world, reserve):
    library, _, _ = world
    reservation = reserve()
    old = reservation.reserved_at - timedelta(days=10)
    notification_service.deliver(db, event_for(reservation, at=old), retention_days=5)
    notification_service.deliver(db, event_for(reservation))

    found = inbox(repo, LIB, library.id)

    assert [n.created_at for n in found] == [reservation.reserved_at]


def test_a_cursor_never_reads_another_inbox(db, repo, world, reserve, make):
    library, reader, _ = world
    other = make.user()
    notification_service.deliver(db, event_for(reserve()))
    notification_service.deliver(db, event_for(reserve(other)))
    _, cursor = repo.list(USER, other.id, now=now(), limit=1)
    foreign = inbox(repo, USER, other.id)[0].id

    for token in filter(None, (cursor, foreign)):
        found, _ = repo.list(USER, reader.id, now=now(), limit=50, cursor=token)
        assert all(n.reservation_id != inbox(repo, USER, other.id)[0].reservation_id for n in found)


@pytest.mark.parametrize("bad", ["%%%", "UkVTIzE"])
def test_a_malformed_cursor_is_rejected(repo, bad):
    with pytest.raises(InvalidReferenceError):
        repo.list(USER, 1, now=now(), cursor=bad)
