"""`persistence/search.py`: documentos, consulta y configuración (sin OpenSearch)."""

import pytest

from app.config import settings
from app.persistence import search
from app.persistence.entities import Author, Book, Genre, PhysicalBook, PhysicalBookStatus
from app.persistence.errors import SearchUnavailableError


def test_a_document_roundtrips_into_the_book_the_api_serves():
    book = Book(
        isbn="9780307474728", title="Cien años de soledad", language="es", pages=471,
        synopsis="Macondo", cover_key="covers/x/1.jpg",
        authors=[Author(id=2, name="García Márquez")], genres=[Genre(id=1, name="Novela")],
    )
    copies = [PhysicalBook(id=i, isbn=book.isbn, library_id=i, library_city=c)
              for i, c in enumerate(["Rosario", "Rosario", "Córdoba"], start=1)]

    document = search.book_document(book, copies)
    rebuilt = search.book_from_document(document)

    assert document["available_cities"] == ["Córdoba", "Rosario"]  # únicas y ordenadas
    assert document["available_copies"] == 3
    assert document["title_sort"] == book.title
    assert (rebuilt.isbn, rebuilt.title, rebuilt.pages, rebuilt.synopsis, rebuilt.cover_key) == (
        book.isbn, book.title, 471, "Macondo", "covers/x/1.jpg"
    )
    assert rebuilt.authors == book.authors and rebuilt.genres == book.genres


def test_unset_optional_fields_are_left_out_of_the_document():
    document = search.book_document(Book(isbn="9780307474728", title="T", language="es"), [])
    assert not {"pages", "synopsis", "cover_key"} & set(document)
    assert document["available_cities"] == [] and document["available_copies"] == 0


def test_only_available_copies_are_expected_by_the_builder():
    """El builder no filtra por estado: quien lo llama pasa los disponibles (ver el indexador)."""
    lost = PhysicalBook(id=1, isbn="x", library_id=1, library_city="Salta", status=PhysicalBookStatus.lost)
    assert search.book_document(Book(isbn="x" * 13, title="T", language="es"), [lost])["available_copies"] == 1


def test_free_text_is_always_a_multi_match_never_a_query_string():
    """`query_string` interpreta operadores del usuario (`*`, `AND`, `~`): ROADMAP §5.3."""
    query = search.text_query("Borges OR *")
    assert list(query) == ["multi_match"]
    assert query["multi_match"]["query"] == "Borges OR *"
    assert query["multi_match"]["operator"] == "and"
    assert "query_string" not in repr(query)
    assert {"title^3", "authors.name^2", "isbn", "synopsis"} == set(query["multi_match"]["fields"])


def test_the_index_cannot_be_built_without_a_url(monkeypatch):
    monkeypatch.setattr(settings, "opensearch_url", "")
    assert search.is_enabled() is False
    with pytest.raises(SearchUnavailableError, match="not configured"):
        search.build_index()


def test_the_index_is_built_from_the_settings(monkeypatch):
    monkeypatch.setattr(settings, "opensearch_url", "http://search.example:9200")
    monkeypatch.setattr(settings, "opensearch_index", "mi-indice")
    index = search.build_index()
    assert index.index == "mi-indice"
    assert search.is_enabled() is True
