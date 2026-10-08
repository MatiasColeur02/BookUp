import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.persistence.dynamo import get_db
from app.persistence.entities import User, UserRole
from app.persistence.repositories import UserRepository
from app.services.auth_service import hash_password

from .dynamo_support import temporary_dynamo
from .factories import Factory

PASSWORD = "secret123"


@pytest.fixture(autouse=True)
def disabled_cache(monkeypatch):
    """La suite corre siempre sin cache, tenga o no `REDIS_URL` el entorno.

    Cada test tiene su propia tabla, pero Redis es del entorno y sobrevive entre
    tests: sin esto, correr la suite dentro del contenedor de `docker compose` (que sí
    trae `REDIS_URL`) hace que un test lea el payload cacheado por otro y falle por algo
    que no tiene nada que ver.
    """
    monkeypatch.setattr(settings, "redis_url", "")


@pytest.fixture()
def db():
    """Una tabla `bookup` con sus 4 GSIs, vacía y exclusiva de este test.

    Necesita DynamoDB Local (`docker compose up -d dynamodb`); ver `dynamo_support.py`.
    """
    yield from temporary_dynamo(create_table=True)


@pytest.fixture()
def make(db) -> Factory:
    """Arma estado (autores, libros, ejemplares...) pasando por los repositories."""
    return Factory(db)


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db):
    """Create a user with a known password, straight through the repository."""
    created = 0

    def _make(role: UserRole = UserRole.customer, *, email=None, library_id=None) -> User:
        nonlocal created
        created += 1
        return UserRepository(db).create(
            User(
                email=email or f"{role.value}{created}@example.com",
                password_hash=hash_password(PASSWORD),
                name=f"{role.value.title()} {created}",
                role=role,
                library_id=library_id,
            )
        )

    return _make


@pytest.fixture()
def auth_headers(client):
    """Log a user in and return the Authorization header for them."""

    def _headers(user: User, password: str = PASSWORD) -> dict[str, str]:
        response = client.post("/auth/login", json={"email": user.email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _headers


@pytest.fixture()
def sysadmin_headers(make_user, auth_headers):
    return auth_headers(make_user(UserRole.sysadmin))
