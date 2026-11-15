"""El indexador: del stream de DynamoDB al índice de búsqueda. **Único camino de escritura.**

    python -m app.indexer        # local: un poller que lee el stream de la tabla

En AWS esto es una Lambda con un *event source mapping* al stream (`NEW_AND_OLD_IMAGES`) y
`handler` como punto de entrada; en local, `run()` lee el mismo stream de DynamoDB Local y le
pasa los mismos registros. Un solo camino, así el índice no puede divergir por un dual-write
que quedó a medias (ROADMAP §2 y §5.4).

**Qué reindexa.** Para cada evento determina el ISBN afectado y reconstruye *ese documento
entero* desde DynamoDB (no aplica el delta):

| Evento                                          | ISBN afectado                          |
|-------------------------------------------------|----------------------------------------|
| `BOOK#<isbn>` (META, `AUTHOR#`, `GENRE#`)       | directo                                |
| `COPY#<id>` (alta, baja, cambio de estado)      | el atributo `isbn` del ejemplar        |
| `AUTHOR#` / `GENRE#` / `LIB#` META              | ninguno: el renombre ya reescribe los  |
|                                                 | ítems desnormalizados, y *esos* eventos|
|                                                 | disparan la reindexación               |

Reconstruir en vez de aplicar el delta hace que el indexador sea idempotente: un evento
repetido, o llegado fuera de orden, deja el mismo documento.

**La imagen del evento corrige al índice secundario.** Los ejemplares disponibles de un libro
se leen de GSI2, y un GSI puede ir unos milisegundos detrás de la tabla: si el evento de «se
reservó el último ejemplar» llegara antes de que GSI2 lo refleje, el documento seguiría
ofreciendo una ciudad sin stock hasta el próximo evento del libro. Por eso el estado que trae
el propio evento pisa lo que diga el índice.

**Invalida el cache.** Entre la escritura y su indexación (~1 s) una lectura de `GET /books`
puede cachear la lista vieja por 5 minutos; al terminar de indexar se invalida el catálogo —
después de forzar el refresco del índice, para que la lectura siguiente ya vea lo nuevo.

Un evento que falla hace fallar el lote (y Lambda lo reintenta): conviene una DLQ y
`BisectBatchOnFunctionError` en el mapping, o un evento venenoso congela el shard.
"""

from __future__ import annotations

import logging
from typing import Any

from boto3.dynamodb.types import TypeDeserializer
from . import cache
from .persistence import keys
from .persistence.dynamo import Dynamo, get_dynamo
from .persistence.entities import PhysicalBook, PhysicalBookStatus
from .persistence.repositories import BookRepository, PhysicalBookRepository
from .persistence.repositories import _support as s
from .persistence import search
from .persistence.search import OpenSearchIndex, book_document
from .streams import StreamReader, follow  # noqa: F401 — `StreamReader` se reexporta

logger = logging.getLogger(__name__)

_deserializer = TypeDeserializer()

# isbn → {id del ejemplar → su estado final según los eventos, o `None` si se borró}
Overlay = dict[str, dict[int, PhysicalBook | None]]


def _image(record: dict[str, Any], name: str) -> dict[str, Any] | None:
    raw = record.get("dynamodb", {}).get(name)
    return _deserializer.deserialize({"M": raw}) if raw else None


def affected_books(records: list[dict[str, Any]]) -> Overlay:
    """Los ISBN que hay que reindexar y, de los ejemplares que cambiaron, su estado final."""
    overlay: Overlay = {}
    for record in records:
        key = _image(record, "Keys") or {}
        pk, sk = key.get(keys.PK, ""), key.get(keys.SK, "")

        if pk.startswith("BOOK#"):
            overlay.setdefault(pk.removeprefix("BOOK#"), {})
        elif pk.startswith("COPY#") and sk == keys.META:
            removed = record.get("eventName") == "REMOVE"
            image = _image(record, "OldImage" if removed else "NewImage")
            if not image or "isbn" not in image:
                continue
            copy = s.from_item(PhysicalBook, image)
            overlay.setdefault(copy.isbn, {})[copy.id] = None if removed else copy
        # Todo lo demás (alias, contadores, reservas, enlaces COPY#/RES#) no cambia el catálogo.
    return overlay


def index_books(db: Dynamo, index: OpenSearchIndex, overlay: Overlay) -> int:
    """Reconstruye y escribe el documento de cada ISBN. Devuelve cuántos tocó."""
    upserts, deletes = [], []
    for isbn, changed in overlay.items():
        book = BookRepository(db).get(isbn)
        if book is None:
            deletes.append(isbn)  # el libro se borró
            continue
        available = {
            c.id: c
            for c in PhysicalBookRepository(db).list_all(isbn=isbn, status=PhysicalBookStatus.available)
        }
        for copy_id, copy in changed.items():
            if copy is not None and copy.status is PhysicalBookStatus.available:
                available[copy_id] = copy
            else:
                available.pop(copy_id, None)
        upserts.append(book_document(book, available.values()))

    if upserts:
        index.upsert(upserts)
    if deletes:
        index.delete(deletes)
    return len(upserts) + len(deletes)


def process(db: Dynamo, index: OpenSearchIndex, records: list[dict[str, Any]]) -> int:
    overlay = affected_books(records)
    if not overlay:
        return 0
    touched = index_books(db, index, overlay)
    # Primero hacer visible lo escrito y *recién después* invalidar: OpenSearch refresca cada
    # ~1 s, y si se invalidara antes, una lectura en esa ventana volvería a cachear la lista
    # vieja por 5 minutos — que es justo lo que la invalidación venía a evitar.
    index.refresh()
    cache.invalidate(cache.NS_CATALOG, cache.NS_AVAILABILITY)
    return touched


_index_ensured = False


def handler(event: dict[str, Any], context: Any = None) -> dict[str, int]:
    """Punto de entrada de la Lambda.

    Crea el índice con su mapping antes del primer `upsert` del contenedor. Sin esto, si el
    índice todavía no existe (tabla recién sembrada, el seed escribe antes de reindexar),
    OpenSearch lo crea solo con mapping dinámico: `title_sort` y `available_cities` quedan
    como `text` y el listado y las ciudades fallan. En local no pasa porque `run()` reindexa
    (y crea el índice) antes de seguir el stream.
    """
    global _index_ensured
    index = search.get_index()
    if not _index_ensured:
        index.ensure_index()
        _index_ensured = True
    touched = process(get_dynamo(), index, event.get("Records", []))
    return {"indexed": touched}


# ---------------------------------------------------------------------------
# Local: un poller sobre el stream de DynamoDB Local (`app/streams.py`)
# ---------------------------------------------------------------------------


def run(poll_seconds: float = 1.0) -> None:
    """Arranca el poller: engancha el stream, reindexa todo y sigue los cambios.

    Cada vez que engancha un stream (al arrancar, o porque la tabla se recreó) reindexa todo:
    no hay checkpoint, y es la forma de no perder lo que pasó mientras no estaba.
    """
    from .reindex import reindex  # evita el ciclo: reindex usa lo de este módulo

    db, index = get_dynamo(), search.get_index()

    def on_records(records: list[dict[str, Any]]) -> None:
        logger.info("Indexed %d books from %d events", process(db, index, records), len(records))

    follow(
        db,
        on_records,
        on_attach=lambda: logger.info("Initial reindex: %s", reindex(db, index)),
        name="indexer",
        poll_seconds=poll_seconds,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("opensearch").setLevel(logging.WARNING)  # un INFO por request
    run()
