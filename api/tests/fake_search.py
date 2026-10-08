"""Un índice de búsqueda en proceso, con la misma interfaz que `OpenSearchIndex`.

Es el equivalente del `FakeRedis` de `test_cache.py`: deja correr la suite HTTP sin un
OpenSearch y sin esperar su refresco. **Puede divergir del motor real**, y para eso está
`test_search_contract.py`: corre las mismas expectativas contra este fake y contra
OpenSearch de verdad, y un fake que prometa algo que el motor no hace falla ahí.

Modela lo que importa del contrato —texto sin tildes ni mayúsculas, la última palabra como
prefijo, `terms` como OR y filtros como AND, orden por título, total exacto— y nada más.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from app.persistence import keys
from app.persistence.search import book_from_document

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(keys.fold(text))


class FakeSearchIndex:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.exists = False

    # -- escritura ---------------------------------------------------------------

    def ensure_index(self) -> None:
        self.exists = True

    def upsert(self, documents: list[dict[str, Any]]) -> None:
        self.exists = True
        for document in documents:
            self.documents[document["isbn"]] = dict(document)

    def delete(self, isbns: Iterable[str]) -> None:
        for isbn in isbns:
            self.documents.pop(isbn, None)

    def refresh(self) -> None:  # las escrituras ya son visibles
        pass

    def all_isbns(self) -> set[str]:
        return set(self.documents)

    # -- lectura -----------------------------------------------------------------

    def _matches_text(self, document: dict[str, Any], query: str) -> bool:
        terms = _tokens(query)
        if not terms:
            return False  # igual que el motor: una consulta sin palabras no matchea nada
        fields = [document["title"], document["isbn"], document.get("synopsis", "")]
        fields += [a["name"] for a in document.get("authors", [])]
        tokens = [token for field in fields for token in _tokens(field)]

        # `bool_prefix`: todas las palabras exactas y solo la última como prefijo — y solo si
        # el texto termina en una letra o dígito: «Ficc*» ya no es una palabra a medias.
        *whole, last = terms
        last_is_prefix = query.rstrip()[-1:].isalnum()
        return all(term in tokens for term in whole) and (
            any(t.startswith(last) for t in tokens) if last_is_prefix else last in tokens
        )

    def search_books(
        self,
        *,
        query: str | None = None,
        author_ids: list[int] | None = None,
        genre_ids: list[int] | None = None,
        cities: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ):
        found = [
            d
            for d in self.documents.values()
            if (not query or self._matches_text(d, query))
            and (not author_ids or {a["id"] for a in d["authors"]} & set(author_ids))
            and (not genre_ids or {g["id"] for g in d["genres"]} & set(genre_ids))
            and (not cities or set(d["available_cities"]) & set(cities))
        ]
        found.sort(key=lambda d: (keys.fold(d["title"]), d["isbn"]))
        page = found[offset : offset + limit]
        return [book_from_document(d) for d in page], len(found)

    def search_text(self, query: str, limit: int = 50):
        found = [d for d in self.documents.values() if self._matches_text(d, query)]
        return [book_from_document(d) for d in found[:limit]]

    def available_cities(self) -> list[str]:
        return sorted({c for d in self.documents.values() for c in d["available_cities"]})

    def ping(self) -> bool:
        return True
