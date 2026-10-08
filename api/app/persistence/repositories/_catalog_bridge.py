"""PUENTE TEMPORAL entre las fases 4 y 6: filtros y búsqueda del catálogo en memoria.

DynamoDB no sirve `GET /books` (filtros combinables + texto libre) ni `GET /books/search`:
eso es de OpenSearch, y llega con la fase 6 (`persistence/search.py`). Pero la fase 4 corta
los services de SQL, y sin *algo* debajo esos tres endpoints dejarían de andar y la suite
de catálogo con ellos.

Este módulo es ese algo, y **es exactamente la "alternativa descartada" del roadmap §2**:
trae todo el catálogo con un Scan y resuelve filtros, orden y paginación en Python. Sirve
para 71 libros y no más; no escala (límite de 1 MB por página, lee la tabla entera) y no
es búsqueda de texto real. Se borra entero en la fase 6.

Preserva la semántica de las queries SQL que reemplaza: OR dentro de un filtro, AND entre
filtros, "en esta ciudad" = con un ejemplar `available` hoy, orden por título y `total`
exacto. Una diferencia buscada: el texto ya no tiene comodines (`%` y `_` son literales).
"""

from __future__ import annotations

from typing import Any

from .. import keys
from ..dynamo import Dynamo
from ..entities import Book
from . import _support as s


def _load_books(db: Dynamo) -> list[Book]:
    from .book_repository import BookRepository

    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "FilterExpression": "begins_with(PK, :book)",
        "ExpressionAttributeValues": {":book": "BOOK#"},
        "ConsistentRead": True,
    }
    while True:
        page = db.table.scan(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    partitions: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        partitions.setdefault(item[keys.PK], []).append(item)
    books = [b for b in (BookRepository._assemble(p) for p in partitions.values()) if b]
    return sorted(books, key=lambda b: (keys.fold(b.title), b.isbn))


def _available_cities_by_isbn(db: Dynamo) -> dict[str, set[str]]:
    copies = s.query_all(
        db,
        IndexName=keys.GSI1,
        KeyConditionExpression="GSI1PK = :list",
        FilterExpression="#st = :available",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":list": keys.LIST_COPIES, ":available": "available"},
    )
    cities: dict[str, set[str]] = {}
    for copy in copies:
        cities.setdefault(copy["isbn"], set()).add(copy["library_city"])
    return cities


def _matches_text(book: Book, needle: str) -> bool:
    haystacks = [book.title, book.isbn, book.synopsis or "", *(a.name for a in book.authors)]
    return any(needle in h.casefold() for h in haystacks)


def list_filtered(
    db: Dynamo,
    *,
    query: str | None,
    author_ids: list[int],
    genre_ids: list[int],
    cities: list[str],
    limit: int,
    offset: int,
) -> tuple[list[Book], int]:
    books = _load_books(db)
    if query:
        needle = query.casefold()
        books = [b for b in books if _matches_text(b, needle)]
    if author_ids:
        books = [b for b in books if {a.id for a in b.authors} & set(author_ids)]
    if genre_ids:
        books = [b for b in books if {g.id for g in b.genres} & set(genre_ids)]
    if cities:
        by_isbn = _available_cities_by_isbn(db)
        books = [b for b in books if by_isbn.get(b.isbn, set()) & set(cities)]
    return books[offset : offset + limit], len(books)


def search(db: Dynamo, query: str, limit: int) -> list[Book]:
    needle = query.casefold()
    return [b for b in _load_books(db) if _matches_text(b, needle)][:limit]


def available_cities(db: Dynamo) -> list[str]:
    return sorted({c for cities in _available_cities_by_isbn(db).values() for c in cities})
