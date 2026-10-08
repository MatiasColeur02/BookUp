"""Reconstruye el índice de búsqueda entero desde DynamoDB.

    python -m app.reindex

Hace falta en tres casos: el **bootstrap** (tras el seed, o con el índice recién creado), una
**sospecha de divergencia**, y como **reparación** de una cascada de renombre interrumpida. El
índice es descartable por definición: la fuente de verdad es DynamoDB, y esto lo rearma sin
bajarlo (no recrea el índice: reescribe cada documento y borra los que ya no tienen libro).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import cache
from .persistence import keys
from .persistence.dynamo import Dynamo, get_dynamo
from .persistence.entities import PhysicalBook, PhysicalBookStatus
from .persistence.repositories import BookRepository
from .persistence.repositories import _support as s
from .persistence import search
from .persistence.search import OpenSearchIndex, book_document

logger = logging.getLogger(__name__)

WORKERS = 8


@dataclass(frozen=True)
class ReindexResult:
    indexed: int
    removed: int


def _all_isbns(db: Dynamo) -> list[str]:
    items = s.query_all(
        db,
        IndexName=keys.GSI1,
        KeyConditionExpression="GSI1PK = :list",
        ExpressionAttributeValues={":list": keys.LIST_CATALOG},
    )
    return [i["isbn"] for i in items]


def _available_by_isbn(db: Dynamo) -> dict[str, list[PhysicalBook]]:
    """Todos los ejemplares disponibles de la red en una sola query a la lista de ejemplares
    (GSI1), en lugar de una por libro."""
    items = s.query_all(
        db,
        IndexName=keys.GSI1,
        KeyConditionExpression="GSI1PK = :list",
        FilterExpression="#st = :available",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={
            ":list": keys.LIST_COPIES,
            ":available": PhysicalBookStatus.available.value,
        },
    )
    grouped: dict[str, list[PhysicalBook]] = {}
    for item in items:
        copy = s.from_item(PhysicalBook, item)
        grouped.setdefault(copy.isbn, []).append(copy)
    return grouped


def reindex(db: Dynamo | None = None, index: OpenSearchIndex | None = None) -> ReindexResult:
    db = db or get_dynamo()
    index = index or search.get_index()
    index.ensure_index()

    isbns = _all_isbns(db)
    available = _available_by_isbn(db)
    books_repo = BookRepository(db)

    def build(isbn: str) -> dict | None:
        book = books_repo.get(isbn)
        return book_document(book, available.get(isbn, [])) if book else None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        documents = [d for d in pool.map(build, isbns) if d is not None]
    index.upsert(documents)

    # Los documentos de libros que ya no existen.
    stale = index.all_isbns() - {d["isbn"] for d in documents}
    if stale:
        index.delete(stale)
    index.refresh()

    # Lo cacheado hasta ahora sale de un índice anterior.
    cache.invalidate(cache.NS_CATALOG, cache.NS_AVAILABILITY)
    return ReindexResult(indexed=len(documents), removed=len(stale))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("opensearch").setLevel(logging.WARNING)  # un INFO por request
    result = reindex()
    print(f"Reindexed {result.indexed} books, removed {result.removed} stale documents.")


if __name__ == "__main__":
    main()
