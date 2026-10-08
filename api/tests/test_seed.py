"""`python -m app.seed` sobre DynamoDB: dataset completo, determinista, idempotente y con los
contadores en su lugar (ROADMAP §7.4 y §9)."""

from datetime import datetime, timezone

import bcrypt
import pytest

from app import seed as seeding
from app.persistence import keys
from app.persistence.dynamo import Dynamo
from app.persistence.entities import Author, PhysicalBook, PhysicalBookStatus, UserRole
from app.persistence.repositories import (
    AuthorRepository,
    BookRepository,
    GenreRepository,
    LibraryRepository,
    PhysicalBookRepository,
    ReservationRepository,
    UserRepository,
)
from app.persistence.repositories import _support as s

from .dynamo_support import temporary_dynamo

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def seeded():
    """Una tabla sembrada para los tests de solo lectura: sembrar tarda unos segundos, y
    hacerlo una vez por test multiplicaría la suite. Los que escriben usan `fresh`."""
    gen = temporary_dynamo(create_table=True)
    db = next(gen)
    try:
        assert seeding.seed(db, now=NOW) is True
        yield db
    finally:
        gen.close()


@pytest.fixture()
def fresh(db):
    """Una tabla sembrada exclusiva del test, para los que la modifican."""
    assert seeding.seed(db, now=NOW) is True
    return db


def all_books(db: Dynamo):
    """Todos los libros, por la lista del catálogo (GSI1): la fuente de verdad, no el índice."""
    isbns = [
        i["isbn"]
        for i in s.query_all(
            db,
            IndexName=keys.GSI1,
            KeyConditionExpression="GSI1PK = :list",
            ExpressionAttributeValues={":list": keys.LIST_CATALOG},
        )
    ]
    return [BookRepository(db).get(isbn) for isbn in isbns]


def scan(db: Dynamo) -> dict[tuple[str, str], dict]:
    """Toda la tabla. Sin `password_hash`: bcrypt usa una sal nueva en cada corrida."""
    items, kwargs = {}, {"ConsistentRead": True}
    while True:
        page = db.table.scan(**kwargs)
        items.update(
            {
                (i[keys.PK], i[keys.SK]): {k: v for k, v in i.items() if k != "password_hash"}
                for i in page["Items"]
            }
        )
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def test_the_dataset_has_the_documented_size(seeded):
    assert len(LibraryRepository(seeded).list_all()) == len(seeding.LIBRARIES) == 10
    assert len(AuthorRepository(seeded).list_all()) == len(seeding.AUTHORS) == 53
    assert len(GenreRepository(seeded).list_all()) == len(seeding.GENRES) == 16
    assert len(all_books(seeded)) == len(seeding.BOOKS) == 71
    assert len(PhysicalBookRepository(seeded).list_all()) == 398
    # 12 de staff (2 sysadmin + una librarian por sede) y 20 lectores.
    assert len(UserRepository(seeded).list_all()) == 32
    assert len(ReservationRepository(seeded).list_all()) == 193
    assert len(ReservationRepository(seeded).list_all(is_open=True)) == 58


def test_the_seeded_users_can_log_in(seeded):
    repo = UserRepository(seeded)
    admin = repo.get_by_email("admin@bookup.example")
    assert admin.role is UserRole.sysadmin and admin.library_id is None
    assert bcrypt.checkpw(seeding.SEED_PASSWORD.encode(), admin.password_hash.encode())

    sur = repo.get_by_email("sur@bookup.example")
    library = LibraryRepository(seeded).get(sur.library_id)
    assert sur.role is UserRole.librarian and library.name == "Biblioteca Sur"

    ana = repo.get_by_email("ana@bookup.example")
    assert ana.role is UserRole.customer
    # «Mis reservas» de Ana muestra el ciclo completo: abiertas sin retirar y retiradas, devuelta, cancelada.
    mine = ReservationRepository(seeded).list_all(user_id=ana.id)
    assert {(r.picked_up, r.is_open) for r in mine} >= {(False, True), (True, True), (True, False), (False, False)}


def test_running_it_twice_changes_nothing(seeded, capsys):
    before = scan(seeded)

    assert seeding.seed(seeded, now=NOW) is False

    assert "already present" in capsys.readouterr().out
    assert scan(seeded) == before


def test_the_same_seed_gives_the_same_table_on_any_machine():
    """Determinista: dos tablas limpias, mismo reloj, mismos ítems (RNG fijo, ids por orden)."""
    runs = []
    for _ in range(2):
        gen = temporary_dynamo(create_table=True)
        db = next(gen)
        try:
            seeding.seed(db, now=NOW)
            runs.append(scan(db))
        finally:
            gen.close()
    assert runs[0] == runs[1]
    assert len(runs[0]) > 1000


def test_counters_are_left_at_the_last_id_so_the_next_create_is_n_plus_one(fresh):
    seeded = fresh
    """El bug más fácil de la migración: contador en 0 y el primer POST pisa a un sembrado."""
    garcia_marquez = AuthorRepository(seeded).get(1)

    new_author = AuthorRepository(seeded).create(Author(name="Autor Nuevo"))
    assert new_author.id == len(seeding.AUTHORS) + 1
    assert AuthorRepository(seeded).get(1) == garcia_marquez  # no lo pisó

    genre = GenreRepository(seeded).create(seeding.Genre(name="Género Nuevo"))
    assert genre.id == len(seeding.GENRES) + 1
    library = LibraryRepository(seeded).create(
        seeding.Library(name="Nueva", address="X 1", state="BA", city="CABA")
    )
    assert library.id == len(seeding.LIBRARIES) + 1
    user = UserRepository(seeded).create(
        seeding.User(email="nuevo@x.com", password_hash="h", name="N", role=UserRole.customer)
    )
    assert user.id == 33
    copy = PhysicalBookRepository(seeded).create(
        PhysicalBook(isbn=all_books(seeded)[0].isbn, library_id=1)
    )
    assert copy.id == 399
    reservation = ReservationRepository(seeded).create(
        seeding.Reservation(user_id=user.id, physical_book_id=copy.id, expires_at=NOW.replace(year=2030))
    )
    assert reservation.id == 194


def test_the_denormalized_fields_are_consistent_with_their_sources(seeded):
    libraries = {lib.id: lib for lib in LibraryRepository(seeded).list_all()}
    titles = {b.isbn: b.title for b in all_books(seeded)}
    authors = {a.id: a.name for a in AuthorRepository(seeded).list_all()}
    genres = {g.id: g.name for g in GenreRepository(seeded).list_all()}

    for copy in PhysicalBookRepository(seeded).list_all():
        library = libraries[copy.library_id]
        assert (copy.library_name, copy.library_city) == (library.name, library.city)
        assert copy.book_title == titles[copy.isbn]

    for book in all_books(seeded):
        assert book.authors and all(authors[a.id] == a.name for a in book.authors)
        assert book.genres and all(genres[g.id] == g.name for g in book.genres)


def test_copies_and_reservations_agree_on_who_holds_what(seeded):
    copies = {c.id: c for c in PhysicalBookRepository(seeded).list_all()}
    reservations = ReservationRepository(seeded).list_all()

    open_by_copy = {}
    for r in reservations:
        copy = copies[r.physical_book_id]
        assert (r.library_id, r.isbn) == (copy.library_id, copy.isbn)
        if r.is_open:
            assert r.physical_book_id not in open_by_copy, "a copy has at most one open reservation"
            open_by_copy[r.physical_book_id] = r
        else:
            assert (r.returned_at is not None) != (r.cancelled_at is not None)

    for copy in copies.values():
        reservation = open_by_copy.get(copy.id)
        if reservation is None:
            assert copy.open_reservation_id is None
            assert copy.status in (PhysicalBookStatus.available, PhysicalBookStatus.lost)
        else:
            assert copy.open_reservation_id == reservation.id
            expected = PhysicalBookStatus.loaned if reservation.picked_up else PhysicalBookStatus.reserved
            assert copy.status is expected


def test_the_sparse_index_holds_exactly_the_open_reservations(seeded):
    in_index = s.query_all(
        seeded,
        IndexName=keys.GSI4,
        KeyConditionExpression="GSI4PK = :open",
        ExpressionAttributeValues={":open": keys.OPEN},
    )
    open_ids = {r.id for r in ReservationRepository(seeded).list_all(is_open=True)}
    assert {int(i["id"]) for i in in_index} == open_ids


def test_every_reservation_has_its_copy_link_and_the_copy_listing_matches(seeded):
    repo = PhysicalBookRepository(seeded)
    for reservation in ReservationRepository(seeded).list_all()[:25]:
        assert repo.has_reservations(reservation.physical_book_id)
    # Los índices por sede e por libro ven lo mismo que la lista completa.
    total = len(repo.list_all())
    assert sum(len(repo.list_all(library_id=lib.id)) for lib in LibraryRepository(seeded).list_all()) == total


def test_a_table_with_api_data_but_no_seed_is_not_overwritten(db):
    UserRepository(db).create(
        seeding.User(email="real@x.com", password_hash="h", name="Real", role=UserRole.customer)
    )

    with pytest.raises(seeding.SeedConflictError, match="Refusing"):
        seeding.seed(db, now=NOW)

    assert UserRepository(db).get(1).email == "real@x.com"
    assert len(scan(db)) < 10


def test_an_interrupted_seed_can_be_repeated(db, monkeypatch):
    """El centinela va último: si algo falla a mitad, la tabla no queda marcada como hecha."""
    real_write = seeding._write
    calls = []

    def flaky(db_, items):
        calls.append(len(items))
        if len(calls) == 2:  # tras los datos, antes de contadores y centinela
            raise RuntimeError("boom")
        return real_write(db_, items)

    monkeypatch.setattr(seeding, "_write", flaky)
    with pytest.raises(RuntimeError):
        seeding.seed(db, now=NOW)
    assert s.get_item(db, *keys.seed_marker().values()) is None

    monkeypatch.setattr(seeding, "_write", real_write)
    assert seeding.seed(db, now=NOW) is True
    assert len(PhysicalBookRepository(db).list_all()) == 398


def test_the_api_serves_the_seeded_data(fresh, client):
    seeded = fresh
    login = client.post("/auth/login", json={"email": "sur@bookup.example", "password": "bookup123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    page = client.get("/books", params={"limit": 5}).json()
    assert page["total"] == 71 and len(page["items"]) == 5
    # Algún título tiene stock cruzado en varias sedes (los más pedidos están en 4 a 7).
    popular = client.get(f"/books/{seeding.BOOKS and seeding._isbn13(seeding.BOOKS[0][0])}/availability")
    assert len(popular.json()["libraries"]) >= 2

    # El librarian de Sur solo ve las reservas de su sede.
    sur = UserRepository(seeded).get_by_email("sur@bookup.example")
    mine = client.get("/reservations", headers=headers).json()
    assert mine and {r["physical_book_id"] for r in mine} <= {
        c.id for c in PhysicalBookRepository(seeded).list_all(library_id=sur.library_id)
    }

    created = client.post(
        "/authors",
        json={"name": "Autor Nuevo"},
        headers={"Authorization": "Bearer " + client.post(
            "/auth/login", json={"email": "admin@bookup.example", "password": "bookup123"}
        ).json()["access_token"]},
    )
    assert created.status_code == 201 and created.json()["id"] == 54
    assert client.get("/authors/1").json()["name"] == "Gabriel García Márquez"
