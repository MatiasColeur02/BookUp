import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.main import app
from app.persistence.database import Base, get_db
from app.persistence.models import User, UserRole
from app.services.auth_service import hash_password

PASSWORD = "secret123"


@pytest.fixture(autouse=True)
def disabled_cache(monkeypatch):
    """La suite corre siempre sin cache, tenga o no `REDIS_URL` el entorno.

    Cada test levanta una SQLite nueva, pero Redis es del entorno y sobrevive entre
    tests: sin esto, correr la suite dentro del contenedor de `docker compose` (que sí
    trae `REDIS_URL`) hace que un test lea el payload cacheado por otro y falle por algo
    que no tiene nada que ver.
    """
    monkeypatch.setattr(settings, "redis_url", "")


@pytest.fixture()
def engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session(engine):
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(engine):
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db_session):
    """Create a user with a known password, straight through the ORM."""
    created = 0

    def _make(role: UserRole = UserRole.customer, *, email=None, library_id=None) -> User:
        nonlocal created
        created += 1
        user = User(
            email=email or f"{role.value}{created}@example.com",
            password_hash=hash_password(PASSWORD),
            name=f"{role.value.title()} {created}",
            role=role,
            library_id=library_id,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

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
