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
import time
from typing import Any

from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from . import cache
from .persistence import keys
from .persistence.dynamo import Dynamo, get_dynamo
from .persistence.entities import PhysicalBook, PhysicalBookStatus
from .persistence.repositories import BookRepository, PhysicalBookRepository
from .persistence.repositories import _support as s
from .persistence import search
from .persistence.search import OpenSearchIndex, book_document

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


def handler(event: dict[str, Any], context: Any = None) -> dict[str, int]:
    """Punto de entrada de la Lambda."""
    touched = process(get_dynamo(), search.get_index(), event.get("Records", []))
    return {"indexed": touched}


# ---------------------------------------------------------------------------
# Local: un poller sobre el stream de DynamoDB Local
# ---------------------------------------------------------------------------


class StreamReader:
    """Lee el stream de la tabla shard por shard, recordando dónde quedó cada uno.

    No es una librería de consumo (Lambda hace esto sola en AWS): es lo mínimo para tener el
    mismo camino en local. Sin checkpoint persistente — al reiniciar, `app.indexer` reindexa
    todo y sigue desde el final.
    """

    def __init__(self, db: Dynamo, *, start: str = "LATEST"):
        self.db = db
        self.start = start
        self.client = db.streams
        table = db.client.describe_table(TableName=db.table_name)["Table"]
        self.stream_arn = table["LatestStreamArn"]
        self.iterators: dict[str, str | None] = {}
        self.refresh_shards()

    def is_current(self) -> bool:
        """¿Sigue siendo éste el stream de la tabla? Falso si la tabla se borró y se recreó:
        DynamoDB Local no avisa con un error, simplemente el stream viejo deja de recibir."""
        table = self.db.client.describe_table(TableName=self.db.table_name)["Table"]
        return table.get("LatestStreamArn") == self.stream_arn

    def refresh_shards(self) -> None:
        """Toma los shards que todavía no se están leyendo. El primero arranca en `start`;
        los que aparecen después (hijos de uno que se cerró) arrancan desde su principio."""
        shards = self.client.describe_stream(StreamArn=self.stream_arn)["StreamDescription"]["Shards"]
        first = not self.iterators
        for shard in shards:
            shard_id = shard["ShardId"]
            if shard_id in self.iterators:
                continue
            self.iterators[shard_id] = self.client.get_shard_iterator(
                StreamArn=self.stream_arn,
                ShardId=shard_id,
                ShardIteratorType=self.start if first else "TRIM_HORIZON",
            )["ShardIterator"]

    def read(self) -> list[dict[str, Any]]:
        """Los registros nuevos de todos los shards, sin bloquear."""
        records: list[dict[str, Any]] = []
        for shard_id, iterator in list(self.iterators.items()):
            if iterator is None:
                continue
            while iterator:
                page = self.client.get_records(ShardIterator=iterator, Limit=100)
                records.extend(page["Records"])
                iterator = page.get("NextShardIterator")
                if not page["Records"]:
                    break
            self.iterators[shard_id] = iterator
        return records


# Errores que dicen que el stream que se estaba leyendo ya no existe o no se puede retomar:
# la tabla se borró y se recreó (`docker compose` + reset del seed), o el iterador venció.
_STREAM_LOST = {"ResourceNotFoundException", "ExpiredIteratorException", "TrimmedDataAccessException"}


def _bootstrap(db: Dynamo, index: OpenSearchIndex) -> StreamReader:
    """Engancha el stream y reindexa todo.

    El orden importa: primero se toma el iterador al **final** del stream y recién después
    se reindexa, así lo que se escriba mientras dura el reindexado queda en el stream y se
    procesa después. Al revés, se perdería lo ocurrido en el medio.
    """
    from .reindex import reindex  # evita el ciclo: reindex usa lo de este módulo

    reader = StreamReader(db)
    logger.info("Initial reindex: %s", reindex(db, index))
    logger.info("Following the stream of %s", db.table_name)
    return reader


def run(poll_seconds: float = 1.0) -> None:
    """Arranca el poller: engancha el stream, reindexa todo y sigue los cambios."""
    db, index = get_dynamo(), search.get_index()
    reader = _bootstrap(db, index)

    last_refresh = time.monotonic()
    while True:
        try:
            records = reader.read()
            if records:
                logger.info("Indexed %d books from %d events", process(db, index, records), len(records))
            if time.monotonic() - last_refresh > 10:
                if reader.is_current():
                    reader.refresh_shards()
                else:
                    logger.warning("The table was recreated (new stream); starting over")
                    reader = _bootstrap(db, index)
                last_refresh = time.monotonic()
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in _STREAM_LOST:
                logger.exception("Indexer iteration failed; retrying")
            else:
                logger.warning("The stream is gone (%s); starting over", exc.response["Error"]["Code"])
                try:
                    reader = _bootstrap(db, index)
                except Exception:  # noqa: BLE001 — la tabla puede no estar todavía; se reintenta
                    logger.exception("Bootstrap failed; retrying")
        except Exception:  # noqa: BLE001 — el poller no se cae por un evento o un corte de red
            logger.exception("Indexer iteration failed; retrying")
        time.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("opensearch").setLevel(logging.WARNING)  # un INFO por request
    run()
