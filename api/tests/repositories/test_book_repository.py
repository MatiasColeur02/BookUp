import pytest

from app.persistence.dynamo_repositories import BookRepository, PhysicalBookRepository
from app.persistence.dynamo_repositories import _support as s
from app.persistence.entities import Author, Book
from app.persistence.errors import AlreadyExistsError, ConditionFailedError

from .conftest import ISBN


def test_create_and_get_assemble_the_book_with_its_authors_and_genres(db, make):
    borges, bioy = make.author("Borges"), make.author("Bioy Casares")
    ficcion, cuento = make.genre("Ficción"), make.genre("Cuento")

    created = make.book(
        title="Ficciones", pages=200, synopsis="Cuentos", authors=[bioy, borges], genres=[cuento, ficcion]
    )

    book = BookRepository(db).get(ISBN)
    assert book == created
    assert (book.title, book.pages, book.synopsis, book.cover_key) == ("Ficciones", 200, "Cuentos", None)
    # Orden determinista por id, no por orden de inserción.
    assert [a.name for a in book.authors] == ["Borges", "Bioy Casares"]
    assert [g.name for g in book.genres] == ["Ficción", "Cuento"]
    assert book.created_at is not None and book.created_at == book.updated_at


def test_a_book_is_read_with_a_single_query_on_its_partition(db, make, monkeypatch):
    make.book(authors=[make.author()], genres=[make.genre()])
    calls = []
    real_query = db.table.query
    monkeypatch.setattr(type(db.table), "query", lambda self, **kw: calls.append(kw) or real_query(**kw), raising=False)

    BookRepository(db).get(ISBN)

    assert len(calls) == 1 and "IndexName" not in calls[0]


def test_get_missing_book(db):
    assert BookRepository(db).get("9780000000000") is None


def test_duplicate_isbn_is_a_conflict_and_does_not_change_the_existing_book(db, make):
    author = make.author()
    make.book(title="Original", authors=[author])

    with pytest.raises(AlreadyExistsError):
        make.book(title="Otro", authors=[make.author()])

    book = BookRepository(db).get(ISBN)
    assert book.title == "Original" and [a.id for a in book.authors] == [author.id]


def test_duplicated_authors_in_the_input_are_written_once(db, make):
    author = make.author()
    assert len(make.book(authors=[author, author]).authors) == 1


def test_a_book_with_too_many_links_is_rejected(db, make):
    authors = [Author(id=i, name=f"A{i}") for i in range(1, 101)]
    with pytest.raises(ValueError):
        make.book(authors=authors)


def test_update_scalar_fields(db, make):
    repo = BookRepository(db)
    make.book(title="Viejo")
    before = repo.get(ISBN)

    updated = repo.update(ISBN, title="Nuevo", pages=300, language="en")

    assert (updated.title, updated.pages, updated.language) == ("Nuevo", 300, "en")
    assert updated.created_at == before.created_at and updated.updated_at > before.updated_at


def test_update_none_removes_the_attribute(db, make):
    repo = BookRepository(db)
    make.book(cover_key="covers/x/1.jpg", synopsis="algo")

    updated = repo.update(ISBN, cover_key=None)

    assert updated.cover_key is None and updated.synopsis == "algo"
    assert repo.get(ISBN).cover_key is None


def test_update_replaces_the_author_and_genre_associations(db, make):
    a1, a2, a3 = make.author(), make.author(), make.author()
    g1, g2 = make.genre(), make.genre()
    make.book(authors=[a1, a2], genres=[g1])
    repo = BookRepository(db)

    updated = repo.update(ISBN, authors=[a2, a3], genres=[g2])

    assert [a.id for a in updated.authors] == [a2.id, a3.id]
    assert [g.id for g in updated.genres] == [g2.id]
    # Los enlaces que sobraban dejaron de contar para los 409.
    from app.persistence.dynamo_repositories import AuthorRepository, GenreRepository

    assert AuthorRepository(db).has_books(a1.id) is False
    assert AuthorRepository(db).has_books(a3.id) is True
    assert GenreRepository(db).has_books(g1.id) is False


def test_update_with_an_empty_list_clears_the_associations(db, make):
    make.book(authors=[make.author()], genres=[make.genre()])
    updated = BookRepository(db).update(ISBN, authors=[], genres=[])
    assert updated.authors == [] and updated.genres == []


def test_update_without_authors_leaves_them_alone(db, make):
    author = make.author()
    make.book(authors=[author])
    assert BookRepository(db).update(ISBN, title="Otro").authors == [author]


def test_title_update_propagates_to_the_copies_of_that_book_only(db, make):
    make.book(title="Viejo")
    make.book("9780000000002", "Otro libro")
    mine, foreign = make.copy(), make.copy("9780000000002")

    BookRepository(db).update(ISBN, title="Nuevo")

    copies = PhysicalBookRepository(db)
    assert copies.get(mine.id).book_title == "Nuevo"
    assert copies.get(foreign.id).book_title == "Otro libro"


def test_title_update_changes_the_position_in_the_catalog_index(db, make):
    make.book("9780000000001", "Banana")
    make.book("9780000000002", "Cereza")

    BookRepository(db).update("9780000000001", title="Zanahoria")

    titles = [
        i["title"]
        for i in s.query_all(
            db,
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :c",
            ExpressionAttributeValues={":c": "CATALOG"},
        )
    ]
    assert titles == ["Cereza", "Zanahoria"]


def test_update_rejects_unknown_fields_and_missing_books(db):
    with pytest.raises(TypeError):
        BookRepository(db).update(ISBN, color="rojo")
    with pytest.raises(ConditionFailedError):
        BookRepository(db).update("9780000000000", title="x")
    assert BookRepository(db).get("9780000000000") is None  # no lo crea


def test_delete_removes_the_whole_partition(db, make):
    book = make.book(authors=[make.author(), make.author()], genres=[make.genre()])

    BookRepository(db).delete(book)

    assert BookRepository(db).get(ISBN) is None
    leftover = s.query_all(
        db, KeyConditionExpression="PK = :pk", ExpressionAttributeValues={":pk": f"BOOK#{ISBN}"}
    )
    assert leftover == []


def test_has_physical_books(db, make):
    repo = BookRepository(db)
    book = make.book()
    assert repo.has_physical_books(ISBN) is False

    copy = make.copy()
    assert repo.has_physical_books(ISBN) is True

    PhysicalBookRepository(db).delete(copy)
    assert repo.has_physical_books(ISBN) is False
    repo.delete(book)
