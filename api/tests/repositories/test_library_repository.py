import pytest

from app.persistence.repositories import LibraryRepository, PhysicalBookRepository
from app.persistence.entities import Library
from app.persistence.errors import ConditionFailedError


def test_create_get_list(db):
    repo = LibraryRepository(db)
    sur = repo.create(
        Library(name="Sur", address="X 1", state="BA", city="La Plata", hours="9 a 18", phone="123")
    )
    central = repo.create(Library(name="Central", address="Y 2", state="BA", city="CABA"))

    assert (sur.id, central.id) == (1, 2)
    assert repo.get(1) == sur
    assert repo.get(1).hours == "9 a 18" and repo.get(2).hours is None
    assert [lib.name for lib in repo.list_all()] == ["Central", "Sur"]
    assert repo.get(99) is None


def test_get_many(db, make):
    a, b = make.library(), make.library()
    assert {x.id for x in LibraryRepository(db).get_many([a.id, b.id, 99])} == {a.id, b.id}


def test_partial_update_keeps_the_rest_and_none_clears_an_attribute(db, make):
    repo = LibraryRepository(db)
    library = make.library(hours="9 a 18", phone="123")

    updated = repo.update(library.id, phone="456")
    assert updated.phone == "456" and updated.hours == "9 a 18"

    cleared = repo.update(library.id, hours=None)
    assert cleared.hours is None
    assert repo.get(library.id).hours is None and repo.get(library.id).phone == "456"


def test_update_rejects_unknown_fields_and_missing_libraries(db, make):
    with pytest.raises(TypeError):
        LibraryRepository(db).update(make.library().id, color="rojo")
    with pytest.raises(ConditionFailedError):
        LibraryRepository(db).update(404, name="x")


def test_rename_reorders_the_listing(db, make):
    repo = LibraryRepository(db)
    a, b = make.library("Alfa"), make.library("Beta")
    repo.update(a.id, name="Zeta")
    assert [lib.name for lib in repo.list_all()] == ["Beta", "Zeta"]


def test_changing_name_or_city_propagates_to_its_copies_only(db, make):
    make.book()
    mine, other = make.library("Sur", city="Rosario"), make.library("Norte", city="Salta")
    copies = [make.copy(library=mine) for _ in range(3)]
    foreign = make.copy(library=other)

    LibraryRepository(db).update(mine.id, name="Sur Renovada", city="Córdoba")

    repo = PhysicalBookRepository(db)
    for copy in copies:
        stored = repo.get(copy.id)
        assert (stored.library_name, stored.library_city) == ("Sur Renovada", "Córdoba")
    assert repo.get(foreign.id).library_city == "Salta"


def test_changing_another_field_does_not_touch_the_copies(db, make):
    make.book()
    library = make.library(city="Rosario")
    copy = make.copy(library=library)
    LibraryRepository(db).update(library.id, phone="999")
    assert PhysicalBookRepository(db).get(copy.id).library_city == "Rosario"


def test_delete_and_has_physical_books(db, make):
    repo = LibraryRepository(db)
    library = make.library()
    assert repo.has_physical_books(library.id) is False

    make.book()
    copy = make.copy(library=library)
    assert repo.has_physical_books(library.id) is True

    PhysicalBookRepository(db).delete(copy)
    assert repo.has_physical_books(library.id) is False
    repo.delete(library)
    assert repo.get(library.id) is None
