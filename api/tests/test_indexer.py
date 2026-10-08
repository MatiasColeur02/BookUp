"""El indexador: de los eventos del stream de DynamoDB al documento de búsqueda."""

from __future__ import annotations

import pytest
from boto3.dynamodb.types import TypeSerializer

from app import cache, indexer
from app.persistence import keys
from app.persistence.entities import PhysicalBook, PhysicalBookStatus
from app.persistence.repositories import (
    AuthorRepository,
    BookRepository,
    LibraryRepository,
    PhysicalBookRepository,
    ReservationRepository,
)

from .factories import ISBN

serializer = TypeSerializer()


def record(name: str, pk: str, sk: str = "META", new: dict | None = None, old: dict | None = None):
    """Un registro con la forma del stream (valores tipados), como lo reciben Lambda y el poller."""
    body = {"Keys": {k: serializer.serialize(v) for k, v in {"PK": pk, "SK": sk}.items()}}
    if new is not None:
        body["NewImage"] = {k: serializer.serialize(v) for k, v in new.items()}
    if old is not None:
        body["OldImage"] = {k: serializer.serialize(v) for k, v in old.items()}
    return {"eventName": name, "dynamodb": body}


def copy_image(copy_id: int, isbn: str, status: str = "available", city: str = "Rosario"):
    return {"PK": f"COPY#{copy_id}", "SK": "META", "id": copy_id, "isbn": isbn,
            "library_id": 1, "status": status, "library_city": city}


# -- qué ISBN toca cada evento -----------------------------------------------------------


def test_events_on_a_book_partition_touch_that_book():
    overlay = indexer.affected_books(
        [
            record("MODIFY", f"BOOK#{ISBN}"),
            record("INSERT", f"BOOK#{ISBN}", "AUTHOR#4"),  # el renombre de un autor llega así
            record("REMOVE", "BOOK#9780000000002", "GENRE#1"),
        ]
    )
    assert overlay == {ISBN: {}, "9780000000002": {}}


def test_a_copy_event_touches_the_copys_book_and_carries_its_new_state():
    overlay = indexer.affected_books(
        [record("MODIFY", "COPY#7", new=copy_image(7, ISBN, "reserved"), old=copy_image(7, ISBN))]
    )
    assert list(overlay) == [ISBN]
    assert overlay[ISBN][7].status is PhysicalBookStatus.reserved


def test_a_removed_copy_is_marked_as_gone_using_its_old_image():
    overlay = indexer.affected_books([record("REMOVE", "COPY#7", old=copy_image(7, ISBN))])
    assert overlay == {ISBN: {7: None}}


def test_when_a_copy_changes_twice_in_a_batch_the_last_state_wins():
    overlay = indexer.affected_books(
        [
            record("MODIFY", "COPY#7", new=copy_image(7, ISBN, "reserved")),
            record("MODIFY", "COPY#7", new=copy_image(7, ISBN, "available")),
        ]
    )
    assert overlay[ISBN][7].status is PhysicalBookStatus.available


@pytest.mark.parametrize(
    "pk, sk",
    [
        ("AUTHOR#1", "META"),  # el renombre ya reescribió los ítems BOOK#/AUTHOR#, que sí disparan
        ("GENRE#1", "META"),
        ("LIB#1", "META"),  # idem con las copias
        ("USER#1", "META"),
        ("USEREMAIL#a@b.com", "META"),
        ("RES#1", "META"),
        ("COPY#7", "RES#1"),  # enlace ejemplar→reserva: no cambia el catálogo
        ("COUNTER#author", "META"),
        ("SEED", "META"),
    ],
)
def test_events_that_do_not_change_the_catalog_are_ignored(pk, sk):
    assert indexer.affected_books([record("MODIFY", pk, sk, new={"PK": pk, "SK": sk})]) == {}


# -- qué documento escribe ---------------------------------------------------------------


def test_a_book_gets_its_document_built_from_dynamodb(db, make, search_index):
    make.book(authors=[make.author("Borges")], genres=[make.genre("Cuento")], pages=100)
    make.copy(library=make.library(city="Rosario"))
    make.copy(library=make.library(city="Córdoba"))

    indexer.index_books(db, search_index, {ISBN: {}})

    document = search_index.documents[ISBN]
    assert document["title"] == "Cien años de soledad"
    assert document["authors"] == [{"id": 1, "name": "Borges"}]
    assert document["available_cities"] == ["Córdoba", "Rosario"]
    assert document["available_copies"] == 2


def test_a_book_that_no_longer_exists_is_removed_from_the_index(db, make, search_index):
    book = make.book()
    indexer.index_books(db, search_index, {ISBN: {}})
    assert ISBN in search_index.documents

    BookRepository(db).delete(book)
    indexer.index_books(db, search_index, {ISBN: {}})

    assert ISBN not in search_index.documents


def test_the_event_image_overrides_a_secondary_index_that_lags_behind(db, make, search_index):
    """GSI2 puede ir unos ms detrás: el estado que trae el evento manda sobre lo que diga."""
    make.book()
    copy = make.copy(library=make.library(city="Rosario"))
    # El índice secundario todavía ve el ejemplar disponible...
    assert PhysicalBookRepository(db).list_all(isbn=ISBN, status=PhysicalBookStatus.available)

    # ...pero el evento dice que se reservó: la ciudad no puede seguir ofreciéndolo.
    reserved = PhysicalBook(id=copy.id, isbn=ISBN, library_id=copy.library_id,
                            status=PhysicalBookStatus.reserved, library_city="Rosario")
    indexer.index_books(db, search_index, {ISBN: {copy.id: reserved}})

    assert search_index.documents[ISBN]["available_cities"] == []
    assert search_index.documents[ISBN]["available_copies"] == 0


def test_a_copy_the_index_has_not_caught_up_with_yet_is_included_from_the_event(db, make, search_index):
    make.book()
    new_copy = PhysicalBook(id=999, isbn=ISBN, library_id=1, library_city="Salta")

    indexer.index_books(db, search_index, {ISBN: {999: new_copy}})

    assert search_index.documents[ISBN]["available_cities"] == ["Salta"]


def test_a_deleted_copy_stops_counting(db, make, search_index):
    make.book()
    copy = make.copy()
    indexer.index_books(db, search_index, {ISBN: {copy.id: None}})
    assert search_index.documents[ISBN]["available_copies"] == 0


def test_processing_invalidates_the_catalog_cache(db, make, search_index, monkeypatch):
    make.book()
    invalidated = []
    monkeypatch.setattr(cache, "invalidate", lambda *ns: invalidated.append(ns))

    assert indexer.process(db, search_index, [record("MODIFY", f"BOOK#{ISBN}")]) == 1
    assert invalidated == [(cache.NS_CATALOG, cache.NS_AVAILABILITY)]

    invalidated.clear()
    assert indexer.process(db, search_index, [record("MODIFY", "USER#1")]) == 0
    assert invalidated == []  # nada del catálogo cambió: no se tira el cache


def test_the_index_is_refreshed_before_the_cache_is_invalidated(db, make, search_index, monkeypatch):
    """Al revés, una lectura en la ventana de refresco (~1 s) recachearía la lista vieja."""
    make.book()
    order = []
    monkeypatch.setattr(search_index, "refresh", lambda: order.append("refresh"))
    monkeypatch.setattr(cache, "invalidate", lambda *ns: order.append("invalidate"))

    indexer.process(db, search_index, [record("MODIFY", f"BOOK#{ISBN}")])

    assert order == ["refresh", "invalidate"]


def test_the_lambda_entry_point_processes_the_records_of_the_event(db, make, search_index, monkeypatch):
    make.book()
    monkeypatch.setattr(indexer, "get_dynamo", lambda: db)

    result = indexer.handler({"Records": [record("INSERT", f"BOOK#{ISBN}")]}, None)

    assert result == {"indexed": 1} and ISBN in search_index.documents
    assert indexer.handler({"Records": []}) == {"indexed": 0}


# -- de punta a punta, con el stream real de DynamoDB Local -------------------------------


def test_the_whole_pipeline_from_real_stream_events(db, make, search_index):
    """Escribe por los repositories y lee el stream de verdad: las formas de los eventos de
    arriba son las que efectivamente produce la tabla."""
    reader = indexer.StreamReader(db, start="TRIM_HORIZON")

    def sync():
        return indexer.process(db, search_index, reader.read())

    # 1. Un libro con autor y género, y un ejemplar en Rosario.
    author = make.author("Borges")
    book = make.book(authors=[author], genres=[make.genre("Cuento")])
    rosario = make.library(city="Rosario")
    copy = make.copy(library=rosario)
    assert sync() >= 1
    document = search_index.documents[ISBN]
    assert document["authors"][0]["name"] == "Borges"
    assert document["available_cities"] == ["Rosario"]

    # 2. Se reserva el último ejemplar: la ciudad deja de aparecer.
    user = make.user()
    reservation = make.reservation(copy, user)
    sync()
    assert search_index.documents[ISBN]["available_cities"] == []

    # 3. Se cancela: vuelve.
    ReservationRepository(db).cancel(reservation.id)
    sync()
    assert search_index.documents[ISBN]["available_cities"] == ["Rosario"]

    # 4. Renombrar al autor cascadea a los ítems del libro, y ese evento reindexa.
    AuthorRepository(db).update(author.id, name="Jorge Luis Borges")
    sync()
    assert search_index.documents[ISBN]["authors"][0]["name"] == "Jorge Luis Borges"

    # 5. Cambiar la ciudad de la sede reescribe sus ejemplares, y eso reindexa el libro.
    LibraryRepository(db).update(rosario.id, city="Santa Fe")
    sync()
    assert search_index.documents[ISBN]["available_cities"] == ["Santa Fe"]

    # 6. Marcar el ejemplar perdido lo saca del stock.
    PhysicalBookRepository(db).update_status(copy.id, PhysicalBookStatus.lost)
    sync()
    assert search_index.documents[ISBN]["available_copies"] == 0

    # 7. Borrar el ejemplar y después el libro lo saca del índice.
    PhysicalBookRepository(db).delete(copy)
    BookRepository(db).delete(book)
    sync()
    assert ISBN not in search_index.documents

    # Y sin cambios nuevos, el lector no devuelve nada.
    assert reader.read() == []


def test_a_reader_notices_when_the_table_was_dropped_and_recreated(db):
    from app.persistence.table import drop_table, ensure_table

    reader = indexer.StreamReader(db)
    assert reader.is_current() is True

    drop_table(db)
    ensure_table(db)  # misma tabla, stream nuevo

    assert reader.is_current() is False
    assert indexer.StreamReader(db).is_current() is True


def test_a_reader_started_at_latest_only_sees_what_happens_afterwards(db, make):
    make.book()  # antes de enganchar el stream: no se ve
    reader = indexer.StreamReader(db, start="LATEST")
    assert reader.read() == []

    make.book("9780000000002", "Otro")

    seen = {r["dynamodb"]["Keys"]["PK"]["S"] for r in reader.read()}
    assert seen == {"BOOK#9780000000002"}
    assert f"BOOK#{ISBN}" not in seen
