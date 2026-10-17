"""El ciclo de vida de los usuarios con `AUTH_MODE=cognito` (`COGNITO_ROADMAP.md` §4.3 y §5).

La app se arma con `create_app()` ya en modo cognito, porque qué routers existen se decide al
montarla. El token no es lo que se prueba acá (eso es `test_auth_cognito.py`): el usuario del
request se fija con un override de `get_current_user`.
"""

import pytest
from fastapi.testclient import TestClient

from app import identity
from app.config import settings
from app.controllers.dependencies import get_current_user
from app.main import create_app
from app.persistence.dynamo import get_db
from app.persistence.entities import User, UserRole
from app.persistence.repositories import UserRepository

from .fake_identity import cognito  # noqa: F401  (fixture)


@pytest.fixture()
def cognito_mode(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    monkeypatch.setattr(settings, "cognito_user_pool_id", "us-east-1_TestPool")
    monkeypatch.setattr(settings, "cognito_app_client_id", "test-app-client")


class Caller:
    """El usuario autenticado del próximo request."""

    def __init__(self, app):
        self.app = app

    def __call__(self, user: User | None) -> None:
        if user is None:
            self.app.dependency_overrides.pop(get_current_user, None)
        else:
            self.app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture()
def app(cognito_mode, db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return app


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def as_user(app):
    return Caller(app)


@pytest.fixture()
def sysadmin(db, as_user):
    admin = UserRepository(db).create(
        User(email="admin@example.com", name="Admin", role=UserRole.sysadmin, cognito_sub="admin-sub")
    )
    as_user(admin)
    return admin


def staff_payload(**overrides):
    return {
        "email": "biblio@example.com",
        "password": "temporal123",
        "name": "Biblio",
        "role": "librarian",
        **overrides,
    }


# ---------------------------------------------------------------------------
# Routers por modo
# ---------------------------------------------------------------------------


def test_login_and_self_signup_are_not_mounted(client):
    assert client.post("/auth/login", json={"email": "a@b.com", "password": "x" * 8}).status_code == 404
    # `/users` existe (GET, de sysadmin), así que un POST es 405 y no 404: no hay auto-registro.
    signup = client.post("/users", json={"email": "a@b.com", "password": "x" * 8, "name": "A"})
    assert signup.status_code == 405


def test_openapi_reflects_the_mode(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/auth/login" not in paths
    assert "post" not in paths["/users"]
    assert "/auth/me" in paths and "post" in paths["/users/staff"]


def test_local_mode_still_mounts_everything(db):
    paths = TestClient(create_app()).get("/openapi.json").json()["paths"]
    assert "/auth/login" in paths and "post" in paths["/users"]


# ---------------------------------------------------------------------------
# Alta de personal: Cognito y después DynamoDB, con compensación
# ---------------------------------------------------------------------------


def test_create_staff_creates_the_account_and_links_it(client, sysadmin, cognito, make, db):
    library = make.library("Sur", city="Bariloche")

    response = client.post(
        "/users/staff", json=staff_payload(email="Biblio@Example.com", library_id=library.id)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "biblio@example.com"  # normalizado, igual que en Cognito
    assert body["library_id"] == library.id
    account = cognito.accounts["biblio@example.com"]
    assert (account.password, account.permanent) == ("temporal123", False)  # temporal
    user = UserRepository(db).get(body["id"])
    assert user.cognito_sub == account.sub
    assert user.password_hash is None  # la contraseña vive en Cognito, no en la base
    assert UserRepository(db).get_by_cognito_sub(account.sub).id == user.id


def test_create_staff_with_unknown_library_rolls_back_the_account(client, sysadmin, cognito):
    response = client.post("/users/staff", json=staff_payload(library_id=999))

    assert response.status_code == 404
    assert cognito.accounts == {}
    (_, created), (operation, deleted) = cognito.calls
    assert (created, operation) == ("biblio@example.com", "delete_user")
    assert deleted != created  # se compensó por el sub que devolvió el alta, no por el email


def test_create_staff_with_email_already_in_the_database_rolls_back(client, sysadmin, cognito, db):
    # Existe en DynamoDB pero no en Cognito (p. ej. sembrado y sin `seed_cognito`).
    UserRepository(db).create(User(email="biblio@example.com", name="Viejo", role=UserRole.customer))

    response = client.post("/users/staff", json=staff_payload())

    assert response.status_code == 409
    assert cognito.accounts == {}


def test_create_staff_with_email_already_in_cognito_is_a_conflict(client, sysadmin, cognito, db):
    cognito.create_user(email="biblio@example.com", name="Otra", temporary_password="x" * 8)

    response = client.post("/users/staff", json=staff_payload())

    assert response.status_code == 409
    assert response.json()["detail"] == "User with email biblio@example.com already exists"
    assert UserRepository(db).get_by_email("biblio@example.com") is None
    assert "biblio@example.com" in cognito.accounts  # la que ya estaba no se toca


def test_create_staff_with_a_password_cognito_rejects_is_a_422(client, sysadmin, cognito, db):
    response = client.post("/users/staff", json=staff_payload(password="rejected-by-policy"))

    assert response.status_code == 422
    assert UserRepository(db).get_by_email("biblio@example.com") is None


def test_create_staff_with_cognito_down_is_a_503_and_writes_nothing(client, sysadmin, cognito, db):
    cognito.down.add("create_user")

    response = client.post("/users/staff", json=staff_payload())

    assert response.status_code == 503
    assert UserRepository(db).get_by_email("biblio@example.com") is None


def test_failed_rollback_still_reports_the_original_error(client, sysadmin, cognito):
    cognito.down.add("delete_user")

    response = client.post("/users/staff", json=staff_payload(library_id=999))

    assert response.status_code == 404  # el error de la sede, no el de Cognito


def test_create_staff_still_requires_a_sysadmin(client, as_user, db, cognito):
    customer = UserRepository(db).create(
        User(email="c@example.com", name="C", role=UserRole.customer, cognito_sub="c-sub")
    )
    as_user(customer)

    assert client.post("/users/staff", json=staff_payload()).status_code == 403
    assert cognito.calls == []


# ---------------------------------------------------------------------------
# Baja: primero Cognito, después DynamoDB
# ---------------------------------------------------------------------------


def _linked_customer(db, cognito, email="lector@example.com"):
    sub = cognito.ensure_user(email=email, name="Lector", password="bookup123")
    return UserRepository(db).create(
        User(email=email, name="Lector", role=UserRole.customer, cognito_sub=sub)
    )


def test_delete_removes_the_account_first_and_then_the_user(client, as_user, cognito, db, monkeypatch):
    user = _linked_customer(db, cognito)
    as_user(user)
    seen = []

    def delete_in_cognito(username):
        # En el momento de borrar en Cognito, el `User` todavía está en la base.
        seen.append(UserRepository(db).get(user.id) is not None)
        cognito.delete_user(username)

    monkeypatch.setattr(identity, "delete_user", delete_in_cognito)

    assert client.delete(f"/users/{user.id}").status_code == 204
    assert seen == [True]
    assert cognito.by_sub(user.cognito_sub) is None
    assert UserRepository(db).get(user.id) is None
    assert UserRepository(db).get_by_cognito_sub(user.cognito_sub) is None


def test_delete_with_cognito_down_keeps_the_user(client, as_user, cognito, db):
    user = _linked_customer(db, cognito)
    as_user(user)
    cognito.down.add("delete_user")

    assert client.delete(f"/users/{user.id}").status_code == 503
    assert UserRepository(db).get(user.id) is not None


def test_retrying_a_delete_that_failed_in_dynamodb_finishes_it(client, sysadmin, cognito, db, monkeypatch):
    user = _linked_customer(db, cognito)
    real_delete = UserRepository.delete

    def broken(self, u):
        raise RuntimeError("DynamoDB went away")

    monkeypatch.setattr(UserRepository, "delete", broken)
    with pytest.raises(RuntimeError):
        client.delete(f"/users/{user.id}")
    assert cognito.by_sub(user.cognito_sub) is None  # ya no puede entrar
    assert UserRepository(db).get(user.id) is not None

    monkeypatch.setattr(UserRepository, "delete", real_delete)
    assert client.delete(f"/users/{user.id}").status_code == 204  # Cognito: ya no estaba
    assert UserRepository(db).get(user.id) is None


def test_delete_of_a_user_not_yet_linked_goes_by_email(client, sysadmin, cognito, db):
    cognito.ensure_user(email="viejo@example.com", name="Viejo", password="bookup123")
    user = UserRepository(db).create(User(email="viejo@example.com", name="Viejo", role=UserRole.customer))

    assert client.delete(f"/users/{user.id}").status_code == 204
    assert cognito.calls[-1] == ("delete_user", "viejo@example.com")
    assert cognito.accounts == {}


def test_delete_of_a_missing_user_is_a_404_and_does_not_touch_cognito(client, sysadmin, cognito):
    assert client.delete("/users/999").status_code == 404
    assert cognito.calls == []


def test_the_email_can_sign_up_again_after_deleting(client, as_user, cognito, db):
    user = _linked_customer(db, cognito)
    as_user(user)
    client.delete(f"/users/{user.id}")

    # Lo que haría la Hosted UI + el trigger con el mismo email.
    cognito.ensure_user(email=user.email, name="De nuevo", password="bookup123")
    assert "lector@example.com" in cognito.accounts
    assert UserRepository(db).get_by_email(user.email) is None


# ---------------------------------------------------------------------------
# PATCH: la contraseña no se cambia por la API
# ---------------------------------------------------------------------------


def test_patch_with_password_is_a_422(client, as_user, cognito, db):
    user = _linked_customer(db, cognito)
    as_user(user)

    response = client.patch(f"/users/{user.id}", json={"password": "nueva12345", "name": "Otro"})

    assert response.status_code == 422
    assert UserRepository(db).get(user.id).name == "Lector"  # nada a medias


def test_patch_without_password_works_as_always(client, as_user, cognito, db):
    user = _linked_customer(db, cognito)
    as_user(user)

    response = client.patch(f"/users/{user.id}", json={"name": "Nuevo", "language": "en", "password": None})

    assert response.status_code == 200
    assert (response.json()["name"], response.json()["language"]) == ("Nuevo", "en")


def test_sysadmin_changes_role_and_library_as_always(client, sysadmin, cognito, make, db):
    library = make.library("Norte", city="Salta")
    user = _linked_customer(db, cognito)

    response = client.patch(f"/users/{user.id}", json={"role": "librarian", "library_id": library.id})

    assert response.status_code == 200
    assert UserRepository(db).get(user.id).library_id == library.id
