"""El índice de búsqueda del catálogo (OpenSearch): lo que DynamoDB no sabe hacer.

DynamoDB sirve todo acceso por clave conocida, pero no `GET /books?genre_id=1&genre_id=2&
city=Rosario&q=borges`: filtros **combinables** más texto libre. Servirlos con copias de los
ítems exigiría una por combinación (ROADMAP §5). Por eso el catálogo se proyecta a un
documento por libro, y ese documento lleva adentro lo que cambia con el stock:

    {"isbn", "title", "language", "pages", "synopsis", "cover_key",
     "authors": [{"id", "name"}], "genres": [{"id", "name"}],
     "available_cities": ["Buenos Aires", "Rosario"], "available_copies": 7}

`available_cities` adentro del documento es la decisión clave: "en Rosario" significa "con un
ejemplar disponible hoy ahí", y con el campo en el mismo documento `genre_id=1&city=Rosario`
es **una sola query** y no la intersección de dos motores en la aplicación.

**El índice es una proyección de solo lectura y descartable.** La API nunca escribe acá: lo
alimenta únicamente el indexador (`app/indexer.py`, desde el stream de la tabla) y
`app/reindex.py` lo reconstruye entero. Un solo camino de escritura, así no hay un dual-write
que quede a medias. Consecuencia aceptada: `GET /books` es **eventualmente consistente**
(~1 s tras una escritura); `GET /books/{isbn}` no, porque va a DynamoDB.

**Texto libre: `multi_match`, nunca `query_string`.** `query_string` interpreta operadores del
usuario (`*`, `AND`, `~`) y deja armar consultas carísimas a propósito; `multi_match` trata la
entrada como texto. Es el reemplazo del escapado de `%` y `_` que hacía el `ILIKE`.

Sin `OPENSEARCH_URL` la búsqueda queda apagada: los tres endpoints del catálogo responden 503
y el resto de la API funciona igual, como la feature de portadas sin `S3_BUCKET`.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from opensearchpy import OpenSearch
from opensearchpy import exceptions as os_exceptions
from opensearchpy import helpers

from ..config import settings
from .entities import Author, Book, Genre, PhysicalBook
from .errors import SearchUnavailableError

logger = logging.getLogger(__name__)

# OpenSearch no pagina más allá de `from + size` = 10.000 (`index.max_result_window`).
MAX_RESULT_WINDOW = 10_000
BULK_CHUNK = 500

# Campos donde busca el texto libre, con su peso (ROADMAP §5.2).
SEARCH_FIELDS = ["title^3", "authors.name^2", "isbn", "synopsis"]

INDEX_BODY: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        # Un solo nodo en local; en AWS el dominio define sus réplicas.
        "number_of_replicas": 0,
        "analysis": {
            # Sin tildes ni mayúsculas: "garcia marquez" encuentra "García Márquez".
            "analyzer": {
                "folded": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                }
            },
            "normalizer": {
                "folded_keyword": {"type": "custom", "filter": ["lowercase", "asciifolding"]}
            },
        },
    },
    "mappings": {
        # `strict`: un campo que el mapping no conoce es un bug del indexador, no algo que
        # haya que adivinar y mapear solo.
        "dynamic": "strict",
        "properties": {
            "isbn": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "folded"},
            # Orden por título como el `ORDER BY title`: sin distinguir tildes ni mayúsculas.
            "title_sort": {"type": "keyword", "normalizer": "folded_keyword"},
            "language": {"type": "keyword"},
            "pages": {"type": "integer"},
            "synopsis": {"type": "text", "analyzer": "folded"},
            "cover_key": {"type": "keyword", "index": False},
            "authors": {
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "text", "analyzer": "folded"},
                }
            },
            "genres": {
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "text", "analyzer": "folded"},
                }
            },
            # Exacto y con mayúsculas, como el `Library.city IN (...)` de antes.
            "available_cities": {"type": "keyword"},
            "available_copies": {"type": "integer"},
        },
    },
}


# ---------------------------------------------------------------------------
# Documento ↔ entidad
# ---------------------------------------------------------------------------


def book_document(book: Book, available: Iterable[PhysicalBook]) -> dict[str, Any]:
    """El documento de un libro. `available` son sus ejemplares **disponibles** hoy."""
    copies = list(available)
    document: dict[str, Any] = {
        "isbn": book.isbn,
        "title": book.title,
        "title_sort": book.title,
        "language": book.language,
        "authors": [{"id": a.id, "name": a.name} for a in book.authors],
        "genres": [{"id": g.id, "name": g.name} for g in book.genres],
        "available_cities": sorted({c.library_city for c in copies if c.library_city}),
        "available_copies": len(copies),
    }
    # Los opcionales ausentes no se mandan: un `null` y un campo faltante son lo mismo acá.
    for field in ("pages", "synopsis", "cover_key"):
        value = getattr(book, field)
        if value is not None:
            document[field] = value
    return document


def book_from_document(document: dict[str, Any]) -> Book:
    """El `Book` que sirve un resultado de búsqueda, sin ir a DynamoDB a buscarlo."""
    return Book(
        isbn=document["isbn"],
        title=document["title"],
        language=document["language"],
        pages=document.get("pages"),
        synopsis=document.get("synopsis"),
        cover_key=document.get("cover_key"),
        authors=[Author(id=int(a["id"]), name=a["name"]) for a in document.get("authors", [])],
        genres=[Genre(id=int(g["id"]), name=g["name"]) for g in document.get("genres", [])],
    )


def text_query(query: str) -> dict[str, Any]:
    """Texto libre sobre título, autor, ISBN y sinopsis.

    `bool_prefix` con `and`: cada palabra tiene que aparecer, y la última puede estar a
    medias («borg» encuentra «Borges»), que es lo que el `ILIKE '%…%'` daba al escribir.
    """
    return {
        "multi_match": {
            "query": query,
            "type": "bool_prefix",
            "operator": "and",
            "fields": SEARCH_FIELDS,
        }
    }


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------


class OpenSearchIndex:
    """El índice `bookup-books`. Toda falla de red sale como `SearchUnavailableError`."""

    def __init__(self, client: OpenSearch, index: str):
        self.client = client
        self.index = index

    # -- escritura (solo el indexador y `reindex`) ----------------------------

    def ensure_index(self) -> None:
        """Crea el índice con su mapping si no existe. Idempotente."""
        with _translating():
            if not self.client.indices.exists(index=self.index):
                try:
                    self.client.indices.create(index=self.index, body=INDEX_BODY)
                except os_exceptions.RequestError as exc:
                    # Otro proceso lo creó entre el `exists` y el `create`.
                    if "resource_already_exists" not in str(exc.error):
                        raise

    def upsert(self, documents: list[dict[str, Any]]) -> None:
        """Escribe documentos por ISBN (`_id`). Reescribir uno igual no cambia nada."""
        actions = (
            {"_op_type": "index", "_index": self.index, "_id": d["isbn"], "_source": d}
            for d in documents
        )
        with _translating():
            helpers.bulk(self.client, actions, chunk_size=BULK_CHUNK)

    def delete(self, isbns: Iterable[str]) -> None:
        actions = ({"_op_type": "delete", "_index": self.index, "_id": i} for i in isbns)
        with _translating():
            # Borrar lo que ya no está es el caso normal (un evento repetido): no es error.
            helpers.bulk(self.client, actions, chunk_size=BULK_CHUNK, raise_on_error=False)

    def refresh(self) -> None:
        """Hace visibles las escrituras ya. En producción no se llama: alcanza el refresco
        de ~1 s del índice. Lo usan los tests y `reindex`."""
        with _translating():
            self.client.indices.refresh(index=self.index)

    def all_isbns(self) -> set[str]:
        with _translating():
            if not self.client.indices.exists(index=self.index):
                return set()
            hits = helpers.scan(
                self.client, index=self.index, query={"query": {"match_all": {}}, "_source": False}
            )
            return {hit["_id"] for hit in hits}

    # -- lectura (la API) -----------------------------------------------------

    def search_books(
        self,
        *,
        query: str | None = None,
        author_ids: list[int] | None = None,
        genre_ids: list[int] | None = None,
        cities: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Book], int]:
        """Una página del catálogo filtrado y el total que matchea (exacto, no el de la página).

        `terms` es OR dentro de un filtro y cada cláusula de `filter` es AND con las demás:
        la misma semántica de los `EXISTS` que reemplaza.
        """
        filters: list[dict[str, Any]] = []
        if author_ids:
            filters.append({"terms": {"authors.id": author_ids}})
        if genre_ids:
            filters.append({"terms": {"genres.id": genre_ids}})
        if cities:
            filters.append({"terms": {"available_cities": cities}})

        # Más allá de la ventana OpenSearch contesta 400: se devuelve una página vacía con el
        # total, que es lo que da SQL con un `OFFSET` pasado del final.
        beyond_window = offset + limit > MAX_RESULT_WINDOW
        body = {
            "query": {
                "bool": {
                    "must": [text_query(query)] if query else [{"match_all": {}}],
                    "filter": filters,
                }
            },
            "sort": [{"title_sort": "asc"}, {"isbn": "asc"}],
            "from": 0 if beyond_window else offset,
            "size": 0 if beyond_window else limit,
            "track_total_hits": True,
        }
        response = self._search(body)
        total = int(response["hits"]["total"]["value"])
        return [book_from_document(hit["_source"]) for hit in response["hits"]["hits"]], total

    def search_text(self, query: str, limit: int = 50) -> list[Book]:
        """`GET /books/search`: texto libre, los más relevantes primero."""
        body = {"query": text_query(query), "size": limit}
        return [book_from_document(hit["_source"]) for hit in self._search(body)["hits"]["hits"]]

    def available_cities(self) -> list[str]:
        """Ciudades con al menos un ejemplar disponible, para poblar el filtro."""
        body = {
            "size": 0,
            "aggs": {"cities": {"terms": {"field": "available_cities", "size": 1000, "order": {"_key": "asc"}}}},
        }
        response = self._search(body)
        return [b["key"] for b in response.get("aggregations", {}).get("cities", {}).get("buckets", [])]

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except os_exceptions.OpenSearchException:
            return False

    def _search(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            with _translating():
                return self.client.search(index=self.index, body=body)
        except _IndexMissing:
            # Todavía nadie indexó nada (el indexador crea el índice al arrancar): un
            # catálogo vacío, no un error.
            return {"hits": {"total": {"value": 0}, "hits": []}, "aggregations": {}}


class _IndexMissing(Exception):
    pass


class _translating:
    """Traduce las fallas de OpenSearch a las de esta capa."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            return False
        if isinstance(exc, os_exceptions.NotFoundError) and "index_not_found" in str(
            getattr(exc, "error", "")
        ):
            raise _IndexMissing() from exc
        if isinstance(exc, (os_exceptions.ConnectionError, os_exceptions.ConnectionTimeout)):
            raise SearchUnavailableError("The search index is not reachable") from exc
        if isinstance(exc, os_exceptions.TransportError) and isinstance(exc.status_code, int):
            if exc.status_code >= 500 or exc.status_code == 429:
                raise SearchUnavailableError(f"The search index failed ({exc.status_code})") from exc
        if isinstance(exc, helpers.BulkIndexError):
            raise SearchUnavailableError("The search index rejected a bulk write") from exc
        return False


_index: OpenSearchIndex | None = None


def is_enabled() -> bool:
    return bool(settings.opensearch_url)


def build_index() -> OpenSearchIndex:
    """Arma un índice desde `settings`. Sin `OPENSEARCH_URL`, levanta `SearchUnavailableError`."""
    if not is_enabled():
        raise SearchUnavailableError("Search is not configured (OPENSEARCH_URL is empty)")
    client = OpenSearch(
        hosts=[settings.opensearch_url],
        timeout=settings.opensearch_timeout_seconds,
        max_retries=1,
        retry_on_timeout=False,
    )
    return OpenSearchIndex(client, settings.opensearch_index)


def get_index() -> OpenSearchIndex:
    """El índice de la app, armado una vez."""
    global _index
    if _index is None:
        _index = build_index()
    return _index


def health() -> str:
    """Estado del índice para `/health`: `disabled`, `ok` o `down`."""
    if not is_enabled():
        return "disabled"
    try:
        return "ok" if get_index().ping() else "down"
    except SearchUnavailableError:
        return "down"


__all__ = [
    "OpenSearchIndex",
    "book_document",
    "book_from_document",
    "build_index",
    "get_index",
    "health",
    "is_enabled",
]
