"""Acceso a datos del catálogo sobre DynamoDB.

Un libro es una **partición**: el ítem `META` más un ítem por autor y por género
(*adjacency list*, ROADMAP §3.1), con el nombre desnormalizado. Leerlo entero es un solo
`Query` con `PK = BOOK#<isbn>`.

`list_filtered`, `search` y `available_cities` eran queries con `EXISTS`/`ILIKE` y
DynamoDB no las puede servir (filtros combinables + texto libre): la fase 6 las mueve a
OpenSearch (`persistence/search.py`). Hasta entonces las sirve `_catalog_bridge.py`, un
puente en memoria que se borra con esa fase.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..dynamo import Dynamo
from ..entities import Author, Book, Genre
from ..errors import ConditionFailedError
from .. import keys
from . import _catalog_bridge, _support as s

_SCALARS = {"title", "language", "pages", "synopsis", "cover_key"}
_NEW = "attribute_not_exists(PK)"
_EXISTS = "attribute_exists(#pk)"


def _author_link(isbn: str, author: Author) -> dict[str, Any]:
    return {**keys.book_author(isbn, author.id), "author_id": author.id, "author_name": author.name}


def _genre_link(isbn: str, genre: Genre) -> dict[str, Any]:
    return {**keys.book_genre(isbn, genre.id), "genre_id": genre.id, "genre_name": genre.name}


class BookRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    def _partition(self, isbn: str) -> list[dict[str, Any]]:
        return s.query_all(
            self.db,
            ConsistentRead=True,
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": keys.book_pk(isbn)},
        )

    @staticmethod
    def _assemble(items: list[dict[str, Any]]) -> Book | None:
        meta = next((i for i in items if i[keys.SK] == keys.META), None)
        if meta is None:
            return None
        authors = sorted(
            (
                Author(id=int(i["author_id"]), name=i["author_name"])
                for i in items
                if i[keys.SK].startswith(keys.AUTHOR_LINK_PREFIX)
            ),
            key=lambda a: a.id,
        )
        genres = sorted(
            (
                Genre(id=int(i["genre_id"]), name=i["genre_name"])
                for i in items
                if i[keys.SK].startswith(keys.GENRE_LINK_PREFIX)
            ),
            key=lambda g: g.id,
        )
        return s.from_item(Book, meta, authors=authors, genres=genres)

    def get(self, isbn: str) -> Book | None:
        return self._assemble(self._partition(isbn))

    def create(self, book: Book) -> Book:
        """Alta del libro con sus autores y géneros, todo o nada."""
        # Un id repetido sería escribir dos veces el mismo ítem, y la transacción lo rechaza.
        authors = list({a.id: a for a in book.authors}.values())
        genres = list({g.id: g for g in book.genres}.values())
        ops = (
            [
                s.tx_put(
                    {**keys.book(book.isbn, book.title), **s.to_item(_stamped(book), exclude=("authors", "genres"))},
                    condition=_NEW,
                )
            ]
            + [s.tx_put(_author_link(book.isbn, a)) for a in authors]
            + [s.tx_put(_genre_link(book.isbn, g)) for g in genres]
        )
        if len(ops) > s.TRANSACTION_LIMIT:
            raise ValueError(f"A book can have at most {s.TRANSACTION_LIMIT - 1} authors plus genres")
        s.run_transaction(self.db, ops, exists_error=f"Book {book.isbn} already exists")
        return self.get(book.isbn)

    def update(self, isbn: str, **changes: Any) -> Book:
        """Actualización parcial. Un escalar en `None` borra el atributo; `authors` y
        `genres` (listas de entidades) **reemplazan** la asociación entera."""
        unknown = set(changes) - _SCALARS - {"authors", "genres"}
        if unknown:
            raise TypeError(f"Unknown Book fields: {sorted(unknown)}")
        current = self.get(isbn)
        if current is None:
            raise ConditionFailedError(f"Book {isbn} does not exist")

        scalars = {k: v for k, v in changes.items() if k in _SCALARS}
        set_ = {k: v for k, v in scalars.items() if v is not None}
        set_["updated_at"] = s.now()
        if "title" in scalars:
            set_[keys.GSI1_SK] = keys.book(isbn, scalars["title"])[keys.GSI1_SK]

        ops = [
            s.tx_update(
                keys.key(keys.book_pk(isbn)),
                set_=set_,
                remove=[k for k, v in scalars.items() if v is None],
                condition=_EXISTS,
                names={"#pk": keys.PK},
            )
        ]
        ops += _diff_links(
            isbn,
            current.authors,
            changes.get("authors"),
            keys.book_author,
            _author_link,
        )
        ops += _diff_links(
            isbn,
            current.genres,
            changes.get("genres"),
            keys.book_genre,
            _genre_link,
        )
        if len(ops) > s.TRANSACTION_LIMIT:
            raise ValueError("Too many author/genre changes for a single update")
        s.run_transaction(self.db, ops, failed_error=f"Book {isbn} does not exist")

        if "title" in scalars and scalars["title"] != current.title:
            copies = self._copies(isbn)
            s.cascade_set(self.db, s.index_keys(copies), {"book_title": scalars["title"]})
        return self.get(isbn)

    def _copies(self, isbn: str) -> list[dict[str, Any]]:
        return s.query_all(
            self.db,
            IndexName=keys.GSI2,
            KeyConditionExpression="GSI2PK = :book",
            ExpressionAttributeValues={":book": keys.book_pk(isbn)},
        )

    def delete(self, book: Book) -> None:
        """Borra la partición entera: `META` y los enlaces a autores y géneros."""
        items = self._partition(book.isbn)
        ops = [s.tx_delete(keys.key(i[keys.PK], i[keys.SK])) for i in items]
        s.run_in_batches(self.db, ops)

    # -- puente temporal hasta la fase 6 (OpenSearch); ver `_catalog_bridge.py` ------

    def list_filtered(
        self,
        *,
        query: str | None = None,
        author_ids: list[int] | None = None,
        genre_ids: list[int] | None = None,
        cities: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Book], int]:
        """Una página del catálogo filtrado, más el total que matchea (no el de la página)."""
        return _catalog_bridge.list_filtered(
            self.db,
            query=query,
            author_ids=author_ids or [],
            genre_ids=genre_ids or [],
            cities=cities or [],
            limit=limit,
            offset=offset,
        )

    def search(self, query: str, limit: int = 50) -> list[Book]:
        return _catalog_bridge.search(self.db, query, limit)

    def available_cities(self) -> list[str]:
        """Ciudades con al menos un ejemplar disponible, para poblar el filtro."""
        return _catalog_bridge.available_cities(self.db)

    def has_physical_books(self, isbn: str) -> bool:
        return s.exists_any(
            self.db,
            IndexName=keys.GSI2,
            KeyConditionExpression="GSI2PK = :book",
            ExpressionAttributeValues={":book": keys.book_pk(isbn)},
        )


def _stamped(book: Book) -> Book:
    stamp = s.now()
    return dataclasses.replace(book, created_at=stamp, updated_at=stamp)


def _diff_links(isbn, current, new, key_fn, link_fn) -> list[dict[str, Any]]:
    """Ops para pasar de los enlaces actuales a los nuevos: borra los que sobran y suma
    los que faltan. Los que se mantienen no se tocan."""
    if new is None:
        return []
    current_ids = {e.id for e in current}
    new_by_id = {e.id: e for e in new}
    ops = [
        s.tx_delete(keys.key(*_link_key(key_fn(isbn, entity_id))))
        for entity_id in current_ids - new_by_id.keys()
    ]
    ops += [
        s.tx_put(link_fn(isbn, entity)) for entity_id, entity in new_by_id.items()
        if entity_id not in current_ids
    ]
    return ops


def _link_key(item: dict[str, str]) -> tuple[str, str]:
    return item[keys.PK], item[keys.SK]
