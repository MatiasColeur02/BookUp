"""Piezas compartidas: ids, codec, transacciones y cascadas."""

import threading
from datetime import datetime, timezone

import pytest

from app.persistence import keys
from app.persistence.repositories import _support as s
from app.persistence.entities import PhysicalBook, PhysicalBookStatus, Reservation
from app.persistence.errors import AlreadyExistsError, ConditionFailedError


def test_next_id_counts_per_entity(db):
    assert [s.next_id(db, "author") for _ in range(3)] == [1, 2, 3]
    assert s.next_id(db, "genre") == 1


def test_next_id_never_repeats_under_concurrency(db):
    results, lock = [], threading.Lock()

    def worker():
        for _ in range(10):
            value = s.next_id(db, "author")
            with lock:
                results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == list(range(1, 81))


def test_codec_round_trips_enums_datetimes_and_omits_none():
    when = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
    reservation = Reservation(id=7, user_id=1, physical_book_id=2, expires_at=when, library_id=3)

    item = s.to_item(reservation)

    assert item["expires_at"] == "2026-01-02T03:04:05.123456Z"
    assert "cancelled_at" not in item and "isbn" not in item  # None no se guarda
    assert s.from_item(Reservation, item) == reservation

    copy = PhysicalBook(id=1, isbn="x", library_id=2, status=PhysicalBookStatus.loaned)
    assert s.to_item(copy)["status"] == "loaned"
    assert s.from_item(PhysicalBook, s.to_item(copy)) == copy


def test_codec_reads_dynamodb_decimals_as_ints(db):
    db.table.put_item(Item={**keys.key("COPY#9"), "id": 9, "isbn": "x", "library_id": 4, "status": "lost"})
    stored = s.get_item(db, "COPY#9")
    assert isinstance(stored["id"], type(stored["library_id"]))  # Decimal
    copy = s.from_item(PhysicalBook, stored)
    assert copy.id == 9 and isinstance(copy.id, int) and copy.library_id == 4
    assert copy.status is PhysicalBookStatus.lost


def test_exists_any_and_query_all_paginate(db):
    for i in range(30):
        db.table.put_item(Item={"PK": "P", "SK": f"S{i:03d}", "pad": "x" * 100_000})
    kwargs = dict(KeyConditionExpression="PK = :pk", ExpressionAttributeValues={":pk": "P"})
    # 30 × 100 KB > 1 MB: un solo Query no alcanza, tiene que seguir `LastEvaluatedKey`.
    assert len(s.query_all(db, **kwargs)) == 30
    assert s.exists_any(db, **kwargs) is True
    assert s.exists_any(db, KeyConditionExpression="PK = :pk", ExpressionAttributeValues={":pk": "none"}) is False


def test_batch_get_handles_more_than_100_keys_and_duplicates(db):
    for i in range(120):
        db.table.put_item(Item=keys.key(f"X#{i}"))
    wanted = [keys.key(f"X#{i}") for i in range(120)] + [keys.key("X#0"), keys.key("X#missing")]
    assert len(s.batch_get(db, wanted)) == 120


def test_transaction_translates_failed_conditions(db):
    db.table.put_item(Item=keys.key("U#1"))
    put = s.tx_put(keys.key("U#1"), condition="attribute_not_exists(PK)")

    with pytest.raises(AlreadyExistsError, match="taken"):
        s.run_transaction(db, [put], exists_error="taken")
    # Sin `exists_error`, la misma falla es una condición no cumplida cualquiera.
    with pytest.raises(ConditionFailedError) as caught:
        s.run_transaction(db, [put])
    assert not isinstance(caught.value, AlreadyExistsError)


def test_a_failed_transaction_writes_nothing(db):
    db.table.put_item(Item=keys.key("U#1"))
    with pytest.raises(ConditionFailedError):
        s.run_transaction(
            db,
            [
                s.tx_put(keys.key("U#2")),
                s.tx_put(keys.key("U#1"), condition="attribute_not_exists(PK)"),
            ],
        )
    assert s.get_item(db, "U#2") is None


def test_cascade_set_updates_more_than_a_transaction_holds_and_skips_deleted(db):
    item_keys = [keys.key(f"C#{i}") for i in range(130)]
    for k in item_keys[1:]:
        db.table.put_item(Item=k)  # C#0 no existe: no se tiene que crear

    s.cascade_set(db, item_keys, {"city": "Rosario"})

    assert s.get_item(db, "C#0") is None
    assert all(s.get_item(db, f"C#{i}")["city"] == "Rosario" for i in (1, 64, 129))
