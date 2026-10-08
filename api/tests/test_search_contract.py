"""El contrato del índice de búsqueda, verificado contra el fake **y** contra OpenSearch.

La suite HTTP corre sobre `FakeSearchIndex` (rápido, sin servicio); estos tests son lo que
impide que ese fake mienta: cada expectativa corre dos veces, una por implementación, y si el
motor real hace algo distinto de lo que el fake promete, falla la variante `opensearch`.

Necesita el servicio `search` del compose (`docker compose up -d search`), y falla —no se
saltea— si no está. Usa un índice temporal propio (`bookup-test-<uuid>`) y lo borra al
terminar: no toca el índice de desarrollo.
"""

from __future__ import annotations

import os
import uuid

import pytest
from opensearchpy import OpenSearch

from app.persistence.entities import Author, Book, Genre, PhysicalBook, PhysicalBookStatus
from app.persistence.errors import SearchUnavailableError
from app.persistence.search import INDEX_BODY, OpenSearchIndex, book_document

from .fake_search import FakeSearchIndex

OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL") or "http://localhost:9200"

BORGES = Author(id=1, name="Jorge Luis Borges")
GARCIA_MARQUEZ = Author(id=2, name="Gabriel García Márquez")
CORTAZAR = Author(id=3, name="Julio Cortázar")
FICCION = Genre(id=1, name="Ficción")
NOVELA = Genre(id=2, name="Novela")
CUENTO = Genre(id=3, name="Cuento")


def doc(isbn, title, authors=(), genres=(), cities=(), **extra):
    book = Book(isbn=isbn, title=title, language="es", authors=list(authors), genres=list(genres), **extra)
    copies = [
        PhysicalBook(id=i, isbn=isbn, library_id=i, library_city=city, status=PhysicalBookStatus.available)
        for i, city in enumerate(cities, start=1)
    ]
    return book_document(book, copies)


CATALOG = [
    doc("9788420633107", "Ficciones", [BORGES], [FICCION, CUENTO], ["Buenos Aires", "Rosario"],
        synopsis="Cuentos fantásticos y filosóficos."),
    doc("9780307474728", "Cien años de soledad", [GARCIA_MARQUEZ], [FICCION, NOVELA], ["Rosario"],
        synopsis="La saga de los Buendía en Macondo.", pages=471),
    doc("9788437604947", "Rayuela", [CORTAZAR], [NOVELA], ["Córdoba"]),
    doc("9780143039433", "El Aleph", [BORGES], [FICCION, CUENTO], []),  # sin stock en ninguna ciudad
    doc("9780140449266", "Álvaro y los libros", [], [], ["Rosario"]),
]


@pytest.fixture(params=["fake", "opensearch"])
def index(request):
    """El índice, ya con su mapping y vacío."""
    if request.param == "fake":
        fake = FakeSearchIndex()
        fake.ensure_index()
        yield fake
        return
    client = OpenSearch(hosts=[OPENSEARCH_URL], timeout=10)
    try:
        client.info()
    except Exception:  # noqa: BLE001
        pytest.fail(
            f"no OpenSearch reachable at {OPENSEARCH_URL}: run `docker compose up -d search` "
            "(or set OPENSEARCH_URL)",
            pytrace=False,
        )
    real = OpenSearchIndex(client, f"bookup-test-{uuid.uuid4().hex[:12]}")
    real.ensure_index()
    try:
        yield real
    finally:
        client.indices.delete(index=real.index, ignore_unavailable=True)


@pytest.fixture()
def loaded(index):
    index.upsert(CATALOG)
    index.refresh()
    return index


def isbns(books):
    return [b.isbn for b in books]


def titles(books):
    return [b.title for b in books]


# -- sin datos -------------------------------------------------------------------------


def test_an_empty_index_returns_an_empty_catalog(index):
    assert index.search_books() == ([], 0)
    assert index.search_text("algo") == []
    assert index.available_cities() == []


def test_ensure_index_is_idempotent(index):
    index.ensure_index()
    index.ensure_index()
    assert index.search_books() == ([], 0)


def test_an_index_that_was_never_created_is_an_empty_catalog_not_an_error(request):
    """Entre el arranque de la API y el primer reindexado el índice no existe todavía."""
    client = OpenSearch(hosts=[OPENSEARCH_URL], timeout=10)
    index = OpenSearchIndex(client, f"bookup-test-{uuid.uuid4().hex[:12]}-never-created")
    assert index.search_books() == ([], 0)
    assert index.search_text("algo") == []
    assert index.available_cities() == []
    assert index.all_isbns() == set()


# -- listado, orden y paginación --------------------------------------------------------


def test_list_is_sorted_by_title_ignoring_case_and_accents(loaded):
    books, total = loaded.search_books(limit=100)
    assert total == 5
    # «Álvaro» va con la A, no después de la Z.
    assert titles(books) == [
        "Álvaro y los libros",
        "Cien años de soledad",
        "El Aleph",
        "Ficciones",
        "Rayuela",
    ]


def test_pagination_keeps_the_exact_total(loaded):
    first, total = loaded.search_books(limit=2, offset=0)
    second, _ = loaded.search_books(limit=2, offset=2)
    last, _ = loaded.search_books(limit=2, offset=4)
    assert total == 5
    assert len(first) == len(second) == 2 and len(last) == 1
    assert isbns(first + second + last) == isbns(loaded.search_books(limit=100)[0])


def test_an_offset_past_the_end_is_an_empty_page_with_the_real_total(loaded):
    books, total = loaded.search_books(limit=5, offset=50)
    assert books == [] and total == 5


def test_an_offset_beyond_the_result_window_is_an_empty_page_not_an_error(loaded):
    books, total = loaded.search_books(limit=100, offset=20_000)
    assert books == [] and total == 5


def test_results_carry_everything_the_api_returns(loaded):
    (book,), total = loaded.search_books(query="soledad")
    assert total == 1
    assert (book.isbn, book.title, book.language, book.pages) == (
        "9780307474728",
        "Cien años de soledad",
        "es",
        471,
    )
    assert book.synopsis == "La saga de los Buendía en Macondo."
    assert [(a.id, a.name) for a in book.authors] == [(2, "Gabriel García Márquez")]
    assert sorted((g.id, g.name) for g in book.genres) == [(1, "Ficción"), (2, "Novela")]


def test_optional_fields_that_were_never_set_come_back_as_none(loaded):
    (book,), _ = loaded.search_books(query="Rayuela")
    assert book.pages is None and book.synopsis is None and book.cover_key is None


# -- texto libre ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, expected",
    [
        ("Ficciones", ["Ficciones"]),  # título
        ("ficciones", ["Ficciones"]),  # sin distinguir mayúsculas
        ("soledad", ["Cien años de soledad"]),
        ("cien anos", ["Cien años de soledad"]),  # sin tildes: «anos» encuentra «años»
        ("Cortázar", ["Rayuela"]),  # autor
        ("cortazar", ["Rayuela"]),  # ... sin tilde
        ("garcia marquez", ["Cien años de soledad"]),  # nombre y apellido sin tildes
        ("Gabriel Marquez", ["Cien años de soledad"]),  # palabras salteadas del nombre
        ("9788437604947", ["Rayuela"]),  # ISBN completo
        ("Buendía", ["Cien años de soledad"]),  # sinopsis
        ("buendia macondo", ["Cien años de soledad"]),  # todas las palabras tienen que estar
        ("borg", ["El Aleph", "Ficciones"]),  # la última palabra puede estar a medias
        ("jorge luis bor", ["El Aleph", "Ficciones"]),
        ("jor luis borges", []),  # solo la última palabra puede estar a medias
        ("alvaro", ["Álvaro y los libros"]),  # tilde en el dato, no en la consulta
        ("Ficciones Rayuela", []),  # AND: ningún libro tiene las dos
        ("nomatch", []),
    ],
)
def test_free_text_search(loaded, query, expected):
    books, total = loaded.search_books(query=query, limit=100)
    assert sorted(titles(books)) == sorted(expected)
    assert total == len(expected)
    assert sorted(titles(loaded.search_text(query))) == sorted(expected)


@pytest.mark.parametrize(
    "query",
    [
        "%",
        "_",
        "%%%",
        "' OR '1'='1",
        "'; DROP TABLE books; --",
        "*",  # comodín del lenguaje de consulta: tiene que ser texto, no operador
        "title:Ficciones",  # sintaxis de campo de query_string
        "Ficciones OR Rayuela",  # operador de query_string
        "Ficc*",
        "Fic~1",
        "(((",
        "\\",
    ],
)
def test_punctuation_and_query_syntax_are_text_not_operators(loaded, query):
    """Equivale al escapado de `%` y `_` del `ILIKE`: la entrada del usuario nunca es sintaxis."""
    assert loaded.search_books(query=query)[1] == 0
    assert loaded.search_text(query) == []


def test_search_text_respects_its_limit(loaded):
    assert len(loaded.search_text("a", limit=2)) <= 2
    assert len(loaded.search_text("Rosario", limit=50)) == 0  # la ciudad no es campo de texto


# -- filtros ----------------------------------------------------------------------------


def test_author_filter(loaded):
    assert sorted(titles(loaded.search_books(author_ids=[1])[0])) == ["El Aleph", "Ficciones"]
    assert loaded.search_books(author_ids=[999]) == ([], 0)


def test_repeated_values_in_a_filter_are_an_or(loaded):
    books, total = loaded.search_books(author_ids=[1, 3])
    assert total == 3 and sorted(titles(books)) == ["El Aleph", "Ficciones", "Rayuela"]
    books, total = loaded.search_books(genre_ids=[2, 999])  # uno de los dos no existe
    assert sorted(titles(books)) == ["Cien años de soledad", "Rayuela"]


def test_different_filters_are_an_and(loaded):
    # Borges escribió dos cuentos; Cortázar, en este catálogo, ninguno.
    assert loaded.search_books(author_ids=[1], genre_ids=[3])[1] == 2
    assert loaded.search_books(author_ids=[3], genre_ids=[3]) == ([], 0)
    books, total = loaded.search_books(genre_ids=[1], cities=["Rosario"])
    assert sorted(titles(books)) == ["Cien años de soledad", "Ficciones"]


def test_city_filter_means_available_stock_there(loaded):
    assert sorted(titles(loaded.search_books(cities=["Rosario"])[0])) == [
        "Cien años de soledad",
        "Ficciones",
        "Álvaro y los libros",
    ]
    assert titles(loaded.search_books(cities=["Córdoba"])[0]) == ["Rayuela"]
    assert loaded.search_books(cities=["Narnia"]) == ([], 0)


def test_city_filter_is_exact_and_matches_any_of_several(loaded):
    assert loaded.search_books(cities=["rosario"]) == ([], 0)  # las ciudades no se pliegan
    books, total = loaded.search_books(cities=["Córdoba", "Buenos Aires"])
    assert sorted(titles(books)) == ["Ficciones", "Rayuela"]


def test_text_and_filters_combine_and_paginate_together(loaded):
    books, total = loaded.search_books(query="borges", cities=["Rosario"], limit=1)
    assert titles(books) == ["Ficciones"] and total == 1
    books, total = loaded.search_books(query="borges", limit=1, offset=1)
    assert titles(books) == ["Ficciones"] and total == 2  # el total es el del filtro, no el de la página


# -- ciudades ---------------------------------------------------------------------------


def test_available_cities_are_unique_and_sorted(loaded):
    assert loaded.available_cities() == ["Buenos Aires", "Córdoba", "Rosario"]


# -- escritura --------------------------------------------------------------------------


def test_upserting_the_same_book_replaces_it(loaded):
    loaded.upsert([doc("9788437604947", "Rayuela (edición nueva)", [CORTAZAR], [NOVELA], [])])
    loaded.refresh()

    books, total = loaded.search_books(limit=100)
    assert total == 5  # no se duplicó
    assert "Rayuela (edición nueva)" in titles(books) and "Rayuela" not in titles(books)
    assert loaded.search_books(cities=["Córdoba"]) == ([], 0)  # y perdió su stock


def test_delete_removes_books_and_ignores_the_ones_that_are_gone(loaded):
    loaded.delete(["9788437604947", "9780000000000"])  # el segundo nunca existió
    loaded.refresh()

    assert loaded.search_books(limit=100)[1] == 4
    assert "9788437604947" not in loaded.all_isbns()
    loaded.delete(["9788437604947"])  # un evento repetido no es un error


def test_all_isbns(loaded):
    assert loaded.all_isbns() == {d["isbn"] for d in CATALOG}


# -- diferencias que solo existen contra el motor real ------------------------------------


def test_the_mapping_is_strict_so_an_unknown_field_is_a_bug_not_a_new_column():
    assert INDEX_BODY["mappings"]["dynamic"] == "strict"


def test_an_unreachable_index_is_a_search_unavailable_error_not_a_crash():
    dead = OpenSearchIndex(OpenSearch(hosts=["http://localhost:1"], timeout=1, max_retries=0), "x")
    with pytest.raises(SearchUnavailableError):
        dead.search_books()
    with pytest.raises(SearchUnavailableError):
        dead.available_cities()
    assert dead.ping() is False
