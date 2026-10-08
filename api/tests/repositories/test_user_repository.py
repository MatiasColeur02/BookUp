import pytest

from app.persistence.repositories import UserRepository
from app.persistence.entities import User, UserRole
from app.persistence.errors import AlreadyExistsError, ConditionFailedError


def new_user(email="ana@example.com", **kw) -> User:
    return User(email=email, password_hash="hash", name=kw.pop("name", "Ana"), role=UserRole.customer, **kw)


def test_create_get_and_login_lookup(db):
    repo = UserRepository(db)
    ana = repo.create(new_user())

    assert ana.id == 1 and ana.language == "es" and ana.library_id is None
    assert repo.get(1) == ana
    assert repo.get_by_email("ana@example.com") == ana
    assert repo.get_by_email("nadie@example.com") is None
    assert repo.get(99) is None


def test_duplicate_email_is_a_conflict_and_leaves_no_orphan_user(db):
    repo = UserRepository(db)
    repo.create(new_user())

    with pytest.raises(AlreadyExistsError, match="ana@example.com"):
        repo.create(new_user(name="Otra Ana"))

    assert [u.name for u in repo.list_all()] == ["Ana"]


def test_list_all_is_sorted_by_name(db):
    repo = UserRepository(db)
    repo.create(new_user("z@x.com", name="Zoe"))
    repo.create(new_user("a@x.com", name="Ana"))
    assert [u.name for u in repo.list_all()] == ["Ana", "Zoe"]


def test_update_partial_fields(db):
    repo = UserRepository(db)
    ana = repo.create(new_user())

    updated = repo.update(ana.id, name="Ana María", language="en", password_hash="nuevo")

    assert (updated.name, updated.language, updated.password_hash) == ("Ana María", "en", "nuevo")
    assert repo.get(ana.id) == updated
    assert repo.get_by_email("ana@example.com") == updated


def test_update_role_and_clearing_library_id(db, make):
    library = make.library()
    repo = UserRepository(db)
    staff = repo.create(
        User(email="l@x.com", password_hash="h", name="Lu", role=UserRole.librarian, library_id=library.id)
    )
    assert repo.get(staff.id).library_id == library.id

    demoted = repo.update(staff.id, role=UserRole.customer, library_id=None)

    assert demoted.role is UserRole.customer and demoted.library_id is None
    assert repo.get(staff.id).library_id is None


def test_rename_reorders_the_listing(db):
    repo = UserRepository(db)
    a, z = repo.create(new_user("a@x.com", name="Ana")), repo.create(new_user("z@x.com", name="Zoe"))
    repo.update(a.id, name="Zzz")
    assert [u.name for u in repo.list_all()] == ["Zoe", "Zzz"]


def test_changing_the_email_moves_the_alias(db):
    repo = UserRepository(db)
    ana = repo.create(new_user())

    repo.update(ana.id, email="nueva@example.com")

    assert repo.get_by_email("ana@example.com") is None
    assert repo.get_by_email("nueva@example.com").id == ana.id
    repo.create(new_user("ana@example.com", name="Otra"))  # el viejo quedó libre


def test_changing_the_email_to_a_taken_one_is_a_conflict_and_changes_nothing(db):
    repo = UserRepository(db)
    ana = repo.create(new_user())
    repo.create(new_user("bruno@example.com", name="Bruno"))

    with pytest.raises(AlreadyExistsError):
        repo.update(ana.id, email="bruno@example.com", name="Cambiada")

    assert repo.get(ana.id).name == "Ana"
    assert repo.get_by_email("ana@example.com").id == ana.id


def test_update_validates_fields_and_existence(db):
    with pytest.raises(TypeError):
        UserRepository(db).update(1, shoe_size=42)
    with pytest.raises(ConditionFailedError):
        UserRepository(db).update(404, name="Nadie")


def test_delete_frees_the_email_for_reuse(db):
    repo = UserRepository(db)
    ana = repo.create(new_user())

    repo.delete(ana)

    assert repo.get(ana.id) is None
    assert repo.get_by_email("ana@example.com") is None
    again = repo.create(new_user())  # no queda un alias huérfano bloqueándolo
    assert again.id != ana.id
