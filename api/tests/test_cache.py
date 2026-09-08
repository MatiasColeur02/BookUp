from datetime import datetime, timedelta, timezone

import pytest
import redis

from app import cache
from app.config import settings
from app.persistence.models import Author, Book, Genre, Library, PhysicalBook, UserRole


class FakeRedis:
    """Los cuatro comandos que usa `app.cache`, sin TTL real.

    Lo que se verifica acá es la invalidación por generaciones y el fallback ante un
    Redis caído, no la expiración — de eso se ocupa el propio Redis.
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.fail = False

    def _check(self) -> None:
        if self.fail:
            raise redis.ConnectionError("cache caído")

    def get(self, key: str) -> str | None:
        self._check()
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._check()
        self.store[key] = value

    def ping(self) -> bool:
        self._check()
        return True

    def pipeline(self) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, client: FakeRedis):
        self.client = client
        self.keys: list[str] = []

    def incr(self, key: str) -> "FakePipeline":
        self.keys.append(key)
        return self

    def execute(self) -> None:
        self.client._check()
        for key in self.keys:
            self.client.store[key] = str(int(self.client.store.get(key, "0")) + 1)
        self.keys.clear()


@pytest.fixture()
def fake_cache(monkeypatch):
    """Enciende el cache contra un Redis falso; monkeypatch lo desarma al terminar."""
    fake = FakeRedis()
    monkeypatch.setattr(settings, "redis_url", "redis://fake:6379/0")
    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(cache, "_breaker_until", 0.0)
    return fake


@pytest.fixture()
def catalog(db_session):
    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    author = Author(name="Jorge Luis Borges")
    genre = Genre(name="Ficción")
    db_session.add_all([library, author, genre])
    db_session.flush()

    book = Book(
        isbn="9788420633107",
        title="Ficciones",
        language="es",
        authors=[author],
        genres=[genre],
    )
    db_session.add(book)
    db_session.flush()
    db_session.add(PhysicalBook(isbn=book.isbn, library_id=library.id))
    db_session.commit()
    return book, author, library


def test_read_is_served_from_cache(client, fake_cache, catalog, db_session):
    book, _, _ = catalog
    assert client.get(f"/books/{book.isbn}").json()["title"] == "Ficciones"

    # Escritura por fuera de la API: nadie invalida, así que el hit sigue sirviendo lo
    # viejo. Es la prueba de que la segunda lectura no tocó la base.
    book.title = "El Aleph"
    db_session.commit()

    assert client.get(f"/books/{book.isbn}").json()["title"] == "Ficciones"


def test_write_through_the_api_invalidates(client, fake_cache, catalog, sysadmin_headers):
    book, _, _ = catalog
    client.get(f"/books/{book.isbn}")

    response = client.patch(
        f"/books/{book.isbn}", json={"title": "El Aleph"}, headers=sysadmin_headers
    )
    assert response.status_code == 200

    assert client.get(f"/books/{book.isbn}").json()["title"] == "El Aleph"


def test_author_write_invalidates_the_book_payload(
    client, fake_cache, catalog, sysadmin_headers
):
    """`BookOut` embebe los autores: renombrar uno tiene que refrescar el catálogo."""
    book, author, _ = catalog
    assert client.get(f"/books/{book.isbn}").json()["authors"][0]["name"] == "Jorge Luis Borges"

    response = client.patch(
        f"/authors/{author.id}", json={"name": "J. L. Borges"}, headers=sysadmin_headers
    )
    assert response.status_code == 200

    assert client.get(f"/books/{book.isbn}").json()["authors"][0]["name"] == "J. L. Borges"


def test_reserving_invalidates_availability(
    client, fake_cache, catalog, make_user, auth_headers
):
    book, _, _ = catalog
    first = client.get(f"/books/{book.isbn}/availability").json()
    assert first["libraries"][0]["available_copies"] == 1
    physical_book_id = first["libraries"][0]["physical_book_id"]

    headers = auth_headers(make_user(UserRole.customer))
    response = client.post(
        "/reservations",
        json={
            "physical_book_id": physical_book_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 201

    assert client.get(f"/books/{book.isbn}/availability").json()["libraries"] == []


def test_falls_back_to_the_database_when_redis_is_down(client, fake_cache, catalog):
    fake_cache.fail = True

    response = client.get(f"/books/{catalog[0].isbn}")

    assert response.status_code == 200
    assert response.json()["title"] == "Ficciones"


def test_breaker_stops_hitting_a_dead_cache(client, fake_cache, catalog):
    fake_cache.fail = True
    client.get(f"/books/{catalog[0].isbn}")

    # Aunque Redis vuelva, el breaker sigue abierto: nada se escribe hasta que enfríe.
    fake_cache.fail = False
    client.get(f"/books/{catalog[0].isbn}")

    assert fake_cache.store == {}


def test_a_miss_does_not_cache_a_404(client, fake_cache):
    assert client.get("/books/0000000000000").status_code == 404
    assert fake_cache.store == {}
