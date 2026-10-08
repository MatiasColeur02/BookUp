import pytest

from app.persistence.dynamo_repositories import AuthorRepository, BookRepository
from app.persistence.entities import Author
from app.persistence.errors import ConditionFailedError


def test_create_assigns_sequential_ids_and_get_reads_them_back(db):
    repo = AuthorRepository(db)
    first = repo.create(Author(name="Jorge Luis Borges"))
    second = repo.create(Author(name="Julio Cortázar"))

    assert (first.id, second.id) == (1, 2)
    assert repo.get(1) == first
    assert repo.get(99) is None


def test_homonyms_are_allowed_the_id_is_the_identity(db):
    repo = AuthorRepository(db)
    a, b = repo.create(Author(name="Juan Pérez")), repo.create(Author(name="Juan Pérez"))
    assert a.id != b.id
    assert [x.id for x in repo.list_all()] == [a.id, b.id]


def test_list_all_is_sorted_by_name_ignoring_case_and_accents(db):
    repo = AuthorRepository(db)
    for name in ["Zapata", "álvaro", "Borges", "Álvarez"]:
        repo.create(Author(name=name))
    assert [a.name for a in repo.list_all()] == ["Álvarez", "álvaro", "Borges", "Zapata"]


def test_get_many_returns_only_the_ones_that_exist(db, make):
    a, b = make.author(), make.author()
    repo = AuthorRepository(db)
    assert {x.id for x in repo.get_many([a.id, b.id, 999])} == {a.id, b.id}
    assert repo.get_many([]) == []


def test_update_renames_and_reorders_the_listing(db, make):
    repo = AuthorRepository(db)
    a, z = make.author("Ana"), make.author("Zoe")
    assert [x.name for x in repo.list_all()] == ["Ana", "Zoe"]

    renamed = repo.update(a.id, name="Zzz")

    assert renamed == Author(id=a.id, name="Zzz")
    assert repo.get(a.id).name == "Zzz"
    assert [x.name for x in repo.list_all()] == ["Zoe", "Zzz"]


def test_update_propagates_the_name_to_every_book_of_the_author(db, make):
    author, other = make.author("Borges"), make.author("Bioy")
    make.book("9780000000001", "Ficciones", authors=[author, other])
    make.book("9780000000002", "El Aleph", authors=[author])
    make.book("9780000000003", "Otro", authors=[other])

    AuthorRepository(db).update(author.id, name="Jorge Luis Borges")

    books = BookRepository(db)
    assert {a.name for a in books.get("9780000000001").authors} == {"Jorge Luis Borges", "Bioy"}
    assert books.get("9780000000002").authors[0].name == "Jorge Luis Borges"
    assert books.get("9780000000003").authors[0].name == "Bioy"


def test_update_propagates_to_more_books_than_one_transaction_holds(db, make):
    author = make.author("Prolífico")
    for i in range(105):
        make.book(f"97800000{i:05d}", f"Libro {i}", authors=[author])

    AuthorRepository(db).update(author.id, name="Renombrado")

    books = BookRepository(db)
    assert all(books.get(f"97800000{i:05d}").authors[0].name == "Renombrado" for i in (0, 52, 104))


def test_update_of_a_missing_author_fails(db):
    with pytest.raises(ConditionFailedError):
        AuthorRepository(db).update(404, name="Nadie")
    assert AuthorRepository(db).get(404) is None  # y no lo crea


def test_delete_removes_the_author(db, make):
    repo = AuthorRepository(db)
    author = make.author()
    repo.delete(author)
    assert repo.get(author.id) is None
    assert repo.list_all() == []


def test_has_books_follows_the_links(db, make):
    repo = AuthorRepository(db)
    author = make.author()
    assert repo.has_books(author.id) is False

    book = make.book(authors=[author])
    assert repo.has_books(author.id) is True

    BookRepository(db).delete(book)
    assert repo.has_books(author.id) is False
