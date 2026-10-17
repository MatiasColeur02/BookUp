"""`AUTH_MODE=cognito`: el access token del User Pool, validado contra su JWKS.

Sin AWS: el par RSA lo genera el test y el JWKS lo sirve un `urlopen` falso, así que
`PyJWKClient` corre de verdad (cache incluido). Ver `COGNITO_ROADMAP.md` §4.2.
"""

import io
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.config import Settings, settings
from app.persistence.entities import User, UserRole
from app.persistence.repositories import UserRepository
from app.services import auth_service

POOL_ID = "us-east-1_TestPool"
CLIENT_ID = "test-app-client"
KID = "test-key-1"
SUB = "0f3c2a9e-1111-4222-8333-444455556666"
ISSUER = f"https://cognito-idp.us-east-1.amazonaws.com/{POOL_ID}"


def _jwk(private_key, kid: str) -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return {**jwk, "kid": kid, "alg": "RS256", "use": "sig"}


class FakeJwks:
    """El endpoint del JWKS del pool: cuenta los pedidos y puede rotar o caerse."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.keys = [_jwk(self.key, KID)]
        self.requests = 0
        self.down = False

    def urlopen(self, request, timeout=None, context=None):
        assert request.full_url == f"{ISSUER}/.well-known/jwks.json"
        self.requests += 1
        if self.down:
            raise urllib.error.URLError("connection refused")
        return io.BytesIO(json.dumps({"keys": self.keys}).encode())


@pytest.fixture()
def jwks(monkeypatch):
    fake = FakeJwks()
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    monkeypatch.setattr(settings, "cognito_region", "us-east-1")
    monkeypatch.setattr(settings, "cognito_user_pool_id", POOL_ID)
    monkeypatch.setattr(settings, "cognito_app_client_id", CLIENT_ID)
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    # El cliente del JWKS es por proceso: cada test arranca sin claves cacheadas.
    auth_service._jwks_client.cache_clear()
    yield fake
    auth_service._jwks_client.cache_clear()


@pytest.fixture()
def cognito_user(db):
    return UserRepository(db).create(
        User(email="ana@example.com", name="Ana", role=UserRole.librarian, cognito_sub=SUB)
    )


def access_token(key, *, kid=KID, algorithm="RS256", **overrides) -> str:
    """Un access token como los que emite Cognito; `overrides` pisa o (con `None`) quita claims."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": SUB,
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "scope": "openid email profile",
        "username": SUB,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(claims, key, algorithm=algorithm, headers=headers)


def me(client, token: str):
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_valid_access_token_resolves_the_user_by_sub(client, jwks, cognito_user):
    response = me(client, access_token(jwks.key))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == cognito_user.id
    # Rol y sede salen de la base, no del token.
    assert body["role"] == "librarian"


def test_role_comes_from_the_database_on_every_request(client, jwks, cognito_user, db):
    token = access_token(jwks.key)
    UserRepository(db).update(cognito_user.id, role=UserRole.sysadmin)

    assert me(client, token).json()["role"] == "sysadmin"


def test_id_token_is_rejected(client, jwks, cognito_user):
    id_token = access_token(jwks.key, token_use="id", client_id=None, aud=CLIENT_ID)
    assert me(client, id_token).status_code == 401


def test_token_of_another_app_client_is_rejected(client, jwks, cognito_user):
    assert me(client, access_token(jwks.key, client_id="another-client")).status_code == 401


def test_token_of_another_issuer_is_rejected(client, jwks, cognito_user):
    other = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_OtherPool"
    assert me(client, access_token(jwks.key, iss=other)).status_code == 401


def test_expired_token_is_rejected(client, jwks, cognito_user):
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    token = access_token(jwks.key, iat=past, exp=past + timedelta(hours=1))

    response = me(client, token)
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


@pytest.mark.parametrize("missing", ["exp", "iss", "sub", "token_use", "client_id"])
def test_token_missing_a_required_claim_is_rejected(client, jwks, cognito_user, missing):
    assert me(client, access_token(jwks.key, **{missing: None})).status_code == 401


def test_token_signed_by_another_key_with_our_kid_is_rejected(client, jwks, cognito_user):
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert me(client, access_token(impostor)).status_code == 401


def test_token_with_another_algorithm_is_rejected(client, jwks, cognito_user):
    # Confusión de algoritmo: un HS256 cuyo "secreto" es la clave pública del JWKS, que
    # cualquiera puede bajar. Si la API leyera `alg` del header, lo daría por bueno.
    public_jwk = json.dumps(jwks.keys[0])
    assert me(client, access_token(public_jwk, algorithm="HS256")).status_code == 401


def test_unsigned_token_is_rejected(client, jwks, cognito_user):
    assert me(client, access_token(None, algorithm="none")).status_code == 401


def test_local_token_is_rejected_in_cognito_mode(client, jwks, cognito_user):
    local, _ = auth_service.create_access_token(cognito_user)
    assert me(client, local).status_code == 401


def test_unknown_sub_is_rejected(client, jwks, cognito_user):
    stranger = "9a8b7c6d-aaaa-4bbb-8ccc-ddddeeeeffff"
    assert me(client, access_token(jwks.key, sub=stranger)).status_code == 401


def test_token_of_a_deleted_user_is_rejected(client, jwks, cognito_user, db):
    token = access_token(jwks.key)
    assert me(client, token).status_code == 200

    UserRepository(db).delete(cognito_user)

    assert me(client, token).status_code == 401


def test_jwks_is_fetched_once_and_cached(client, jwks, cognito_user):
    token = access_token(jwks.key)
    for _ in range(3):
        assert me(client, token).status_code == 200
    assert jwks.requests == 1


def test_unknown_kid_refetches_the_jwks_for_key_rotation(client, jwks, cognito_user):
    assert me(client, access_token(jwks.key)).status_code == 200

    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks.keys.append(_jwk(rotated, "test-key-2"))

    assert me(client, access_token(rotated, kid="test-key-2")).status_code == 200
    assert jwks.requests == 2


def test_kid_not_in_the_jwks_is_rejected(client, jwks, cognito_user):
    assert me(client, access_token(jwks.key, kid="nobody")).status_code == 401
    assert me(client, access_token(jwks.key, kid=None)).status_code == 401


def test_unreachable_jwks_is_a_503_not_a_401(client, jwks, cognito_user):
    jwks.down = True

    response = me(client, access_token(jwks.key))

    assert response.status_code == 503
    assert response.headers["retry-after"]


def test_cognito_mode_without_pool_or_client_does_not_start():
    with pytest.raises(ValidationError, match="COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID"):
        Settings(_env_file=None, auth_mode="cognito")
    with pytest.raises(ValidationError, match="COGNITO_APP_CLIENT_ID"):
        Settings(_env_file=None, auth_mode="cognito", cognito_user_pool_id=POOL_ID)


def test_issuer_and_jwks_url_are_derived():
    config = Settings(
        _env_file=None,
        auth_mode="cognito",
        cognito_region="sa-east-1",
        cognito_user_pool_id="sa-east-1_Abc",
        cognito_app_client_id=CLIENT_ID,
    )
    assert config.cognito_issuer == "https://cognito-idp.sa-east-1.amazonaws.com/sa-east-1_Abc"
    assert config.cognito_jwks_url == f"{config.cognito_issuer}/.well-known/jwks.json"
