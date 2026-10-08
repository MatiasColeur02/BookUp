import pytest

from app.persistence.dynamo_repositories import BookRepository, GenreRepository
from app.persistence.entities import Genre
from app.persistence.errors import AlreadyExistsError, ConditionFailedError


def test_create_get_and_get_by_name(db):
    repo = GenreRepository(db)
    novela = repo.create(Genre(name="Novela"))
    assert novela.id == 1
    assert repo.get(1) == novela
    assert repo.get_by_name("Novela") == novela
    assert repo.get_by_name("Cuento") is None
    assert repo.get(99) is None


def test_duplicate_name_is_rejected_and_creates_nothing(db):
    repo = GenreRepository(db)
    repo.create(Genre(name="Novela"))

    with pytest.raises(AlreadyExistsError):
        repo.create(Genre(name="Novela"))

    assert [g.name for g in repo.list_all()] == ["Novela"]


def test_name_uniqueness_is_exact_like_the_unique_constraint(db):
    repo = GenreRepository(db)
    repo.create(Genre(name="Novela"))
    repo.create(Genre(name="novela"))  # distinto string, distinto género (como el UNIQUE)
    assert len(repo.list_all()) == 2


def test_list_all_is_sorted_by_name(db):
    repo = GenreRepository(db)
    for name in ["Poesía", "Ensayo", "Novela"]:
        repo.create(Genre(name=name))
    assert [g.name for g in repo.list_all()] == ["Ensayo", "Novela", "Poesía"]


def test_get_many(db, make):
    a, b = make.genre(), make.genre()
    repo = GenreRepository(db)
    assert {g.id for g in repo.get_many([a.id, b.id, 999])} == {a.id, b.id}
    assert repo.get_many([]) == []


def test_rename_moves_the_uniqueness_alias(db, make):
    repo = GenreRepository(db)
    genre = make.genre("Novela")

    repo.update(genre.id, name="Narrativa")

    assert repo.get(genre.id).name == "Narrativa"
    assert repo.get_by_name("Narrativa").id == genre.id
    assert repo.get_by_name("Novela") is None
    # El nombre viejo quedó libre y el nuevo ocupado.
    repo.create(Genre(name="Novela"))
    with pytest.raises(AlreadyExistsError):
        repo.create(Genre(name="Narrativa"))


def test_rename_to_a_taken_name_fails_before_touching_anything(db, make):
    repo = GenreRepository(db)
    novela, cuento = make.genre("Novela"), make.genre("Cuento")
    make.book(genres=[novela])

    with pytest.raises(AlreadyExistsError):
        repo.update(novela.id, name="Cuento")

    assert repo.get(novela.id).name == "Novela"
    assert repo.get_by_name("Novela").id == novela.id
    assert BookRepository(db).get("9780307474728").genres[0].name == "Novela"
    assert repo.get_by_name("Cuento").id == cuento.id


def test_rename_to_the_same_name_is_a_noop_that_still_succeeds(db, make):
    genre = make.genre("Novela")
    assert GenreRepository(db).update(genre.id, name="Novela") == genre


def test_rename_propagates_to_books(db, make):
    genre = make.genre("Novela")
    make.book("9780000000001", "Uno", genres=[genre])
    make.book("9780000000002", "Dos", genres=[genre])

    GenreRepository(db).update(genre.id, name="Narrativa")

    books = BookRepository(db)
    assert books.get("9780000000001").genres[0].name == "Narrativa"
    assert books.get("9780000000002").genres[0].name == "Narrativa"


def test_update_of_a_missing_genre_fails(db):
    with pytest.raises(ConditionFailedError):
        GenreRepository(db).update(404, name="Nada")


def test_delete_frees_the_name(db, make):
    repo = GenreRepository(db)
    genre = make.genre("Novela")
    repo.delete(genre)

    assert repo.get(genre.id) is None
    assert repo.get_by_name("Novela") is None
    repo.create(Genre(name="Novela"))  # se puede reusar


def test_has_books(db, make):
    repo = GenreRepository(db)
    genre = make.genre()
    assert repo.has_books(genre.id) is False
    make.book(genres=[genre])
    assert repo.has_books(genre.id) is True
