from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.persistence.models import UserRole
from tests.conftest import PASSWORD


def test_login_returns_a_token(client, make_user):
    user = make_user()
    response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.jwt_expire_minutes * 60

    claims = jwt.decode(
        body["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "customer"


def test_login_with_wrong_password(client, make_user):
    user = make_user()
    response = client.post("/auth/login", json={"email": user.email, "password": "wrongpassword"})
    assert response.status_code == 401


def test_login_with_unknown_email(client):
    response = client.post("/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert response.status_code == 401


def test_me_returns_the_current_user(client, make_user, auth_headers):
    user = make_user(UserRole.librarian)
    response = client.get("/auth/me", headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["role"] == "librarian"
    assert "password_hash" not in body


def test_me_without_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_with_malformed_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_me_with_expired_token(client, make_user):
    user = make_user()
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "library_id": None,
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_token_signed_with_another_secret_is_rejected(client, make_user):
    user = make_user()
    forged = jwt.encode({"sub": str(user.id)}, "another-secret", algorithm="HS256")

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_token_of_a_deleted_user_is_rejected(client, make_user, auth_headers, db_session):
    user = make_user()
    headers = auth_headers(user)

    db_session.delete(user)
    db_session.commit()

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
