"""El exportador de analítica: filas planas listas para Athena, y archivos que se reescriben."""

from __future__ import annotations

import json

from app.analytics import exporter
from app.persistence.repositories import ReservationRepository
from app.persistence.entities import CancelledBy


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body


def lines(body: bytes) -> list[dict]:
    return [json.loads(line) for line in body.decode().splitlines()]


def test_reservation_rows_carry_library_and_status(db, make):
    lib = make.library("Biblioteca Sur", city="Rosario")
    make.book()
    copy = make.copy(library=lib)
    reservation = make.reservation(copy=copy)

    rows = exporter.build(db)[exporter.RESERVATIONS_KEY]

    assert len(rows) == 1
    row = rows[0]
    assert row["reservation_id"] == reservation.id
    assert row["library_name"] == "Biblioteca Sur"
    assert row["library_city"] == "Rosario"
    assert row["status"] == "reserved"
    assert row["reserved_month"] == reservation.reserved_at.strftime("%Y-%m")
    assert "email" not in row and "name" not in row


def test_status_follows_the_lifecycle(db, make):
    repo = ReservationRepository(db)
    lib = make.library()
    make.book()
    loaned = make.reservation(copy=make.copy(library=lib))
    repo.mark_picked_up(loaned.id)
    cancelled = make.reservation(copy=make.copy(library=lib))
    repo.cancel(cancelled.id, by=CancelledBy.user)

    status = {r["reservation_id"]: r["status"] for r in exporter.build(db)[exporter.RESERVATIONS_KEY]}

    assert status[loaned.id] == "loaned"
    assert status[cancelled.id] == "cancelled"


def test_books_and_libraries_are_exported(db, make):
    make.library("Biblioteca Norte", city="Salta")
    make.book(isbn="9780307474728", title="Cien años de soledad")

    built = exporter.build(db)

    assert built[exporter.LIBRARIES_KEY][0]["name"] == "Biblioteca Norte"
    assert built[exporter.BOOKS_KEY] == [
        {"isbn": "9780307474728", "title": "Cien años de soledad", "language": "es", "pages": None}
    ]


def test_export_writes_json_lines_and_overwrites(db, make):
    make.book()
    make.reservation()
    s3 = FakeS3()

    first = exporter.export(db, s3, "bucket")
    second = exporter.export(db, s3, "bucket")

    assert first == second  # reescribe la foto: no acumula duplicados
    assert first[exporter.RESERVATIONS_KEY] == 1
    assert len(lines(s3.objects[exporter.RESERVATIONS_KEY])) == 1
    assert s3.objects[exporter.RESERVATIONS_KEY].endswith(b"\n")


def test_empty_table_exports_empty_files(db):
    s3 = FakeS3()

    counts = exporter.export(db, s3, "bucket")

    assert set(counts.values()) == {0}
    assert s3.objects[exporter.RESERVATIONS_KEY] == b""
