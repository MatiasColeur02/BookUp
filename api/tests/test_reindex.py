"""`python -m app.reindex`: reconstruir el índice entero desde DynamoDB."""

import pytest

from app import cache
from app.persistence import search
from app.persistence.entities import PhysicalBookStatus
from app.persistence.errors import SearchUnavailableError
from app.persistence.repositories import PhysicalBookRepository
from app.reindex import ReindexResult, reindex

from .factories import ISBN

OTHER = "9780000000002"


def test_reindex_builds_one_document_per_book_with_the_current_stock(db, make, search_index):
    author, genre = make.author("Borges"), make.genre("Cuento")
    make.book(ISBN, "Ficciones", authors=[author], genres=[genre])
    make.book(OTHER, "Sin stock")
    rosario, cordoba = make.library(city="Rosario"), make.library(city="Córdoba")
    make.copy(ISBN, rosario)
    make.copy(ISBN, rosario)
    make.copy(ISBN, cordoba)
    lost = make.copy(ISBN, cordoba)
    PhysicalBookRepository(db).update_status(lost.id, PhysicalBookStatus.lost)

    assert reindex(db, search_index) == ReindexResult(indexed=2, removed=0)

    ficciones = search_index.documents[ISBN]
    assert ficciones["available_cities"] == ["Córdoba", "Rosario"]
    assert ficciones["available_copies"] == 3  # la perdida no cuenta
    assert ficciones["authors"] == [{"id": author.id, "name": "Borges"}]
    assert search_index.documents[OTHER]["available_cities"] == []
    assert search_index.documents[OTHER]["available_copies"] == 0


def test_reindex_is_idempotent(db, make, search_index):
    make.book()
    make.copy()
    reindex(db, search_index)
    first = dict(search_index.documents)

    assert reindex(db, search_index) == ReindexResult(indexed=1, removed=0)
    assert search_index.documents == first


def test_reindex_repairs_a_diverged_index(db, make, search_index):
    """Documentos viejos, faltantes o de libros que ya no existen: todo vuelve a la verdad."""
    make.book(ISBN, "Real")
    make.copy()
    search_index.upsert(
        [
            {"isbn": ISBN, "title": "Viejo", "title_sort": "Viejo", "language": "es",
             "authors": [], "genres": [], "available_cities": ["Narnia"], "available_copies": 9},
            {"isbn": "9780000000099", "title": "Fantasma", "title_sort": "Fantasma", "language": "es",
             "authors": [], "genres": [], "available_cities": [], "available_copies": 0},
        ]
    )

    result = reindex(db, search_index)

    assert result == ReindexResult(indexed=1, removed=1)
    assert set(search_index.documents) == {ISBN}
    assert search_index.documents[ISBN]["title"] == "Real"
    assert search_index.documents[ISBN]["available_cities"] == ["Rosario"]


def test_reindex_of_an_empty_catalog_clears_the_index(db, search_index):
    search_index.upsert([{"isbn": ISBN, "title": "x", "title_sort": "x", "language": "es",
                          "authors": [], "genres": [], "available_cities": [], "available_copies": 0}])
    assert reindex(db, search_index) == ReindexResult(indexed=0, removed=1)
    assert search_index.documents == {}


def test_reindex_creates_the_index_when_it_does_not_exist_yet(db, make, search_index):
    make.book()
    assert search_index.exists is False
    reindex(db, search_index)
    assert search_index.exists is True


def test_reindex_invalidates_the_catalog_cache(db, search_index, monkeypatch):
    invalidated = []
    monkeypatch.setattr(cache, "invalidate", lambda *ns: invalidated.append(ns))
    reindex(db, search_index)
    assert invalidated == [(cache.NS_CATALOG, cache.NS_AVAILABILITY)]


def test_reindex_uses_the_configured_index_by_default(db, make, search_index):
    make.book()
    reindex(db)  # sin índice explícito: el de `search.get_index()`
    assert ISBN in search_index.documents


def test_reindex_without_a_configured_index_says_so(db, monkeypatch):
    def disabled():
        raise SearchUnavailableError("Search is not configured")

    monkeypatch.setattr(search, "get_index", disabled)
    with pytest.raises(SearchUnavailableError):
        reindex(db)
