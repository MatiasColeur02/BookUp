"""Password verification and JWT issuing/decoding.

Two modes (`settings.auth_mode`, see `COGNITO_ROADMAP.md` §4.2):

- `local`: the API issues its own HS256 tokens (`POST /auth/login`) and `sub` is the
  user's id.
- `cognito`: the User Pool issues RS256 access tokens, verified here against its JWKS, and
  `sub` is the Cognito UUID, resolved through the `USERSUB#<sub>` alias.

Either way the caller ends up as a `User` loaded from the database, so role and branch
come from there and not from the token.

Knows nothing about HTTP: the controllers turn `UnauthorizedError` into a 401.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt

from ..config import settings
from ..persistence.dynamo import Dynamo
from ..persistence.entities import User
from ..persistence.repositories import UserRepository
from .errors import AuthUnavailableError, UnauthorizedError

# Fixed, never read from the token header: trusting `alg` is the algorithm-confusion attack.
_COGNITO_ALGORITHMS = ["RS256"]
# The JWKS is cached for the life of the set; `PyJWKClient` refetches it anyway as soon as a
# token comes with a `kid` it does not know (key rotation), so a long lifespan costs nothing.
_JWKS_LIFESPAN_SECONDS = 24 * 60 * 60
_JWKS_TIMEOUT_SECONDS = 3


def normalize_email(email: str) -> str:
    """El email, como se guarda y se busca. En minúsculas en **todos** los caminos (registro
    local, alta de personal, trigger de Cognito, seed): Cognito lo trata sin distinguir
    mayúsculas y el alias `USEREMAIL#<email>` sí distingue, así que sin esto `Ana@x.com` y
    `ana@x.com` serían una cuenta en Cognito y dos en la base."""
    return email.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def authenticate(db: Dynamo, *, email: str, password: str) -> User:
    user = UserRepository(db).get_by_email(normalize_email(email))
    # Same error for "no such email" and "wrong password", so the endpoint does
    # not leak which emails are registered. A user without a hash (created through
    # Cognito) has no local password at all.
    if (
        user is None
        or user.password_hash is None
        or not verify_password(password, user.password_hash)
    ):
        raise UnauthorizedError("Invalid email or password")
    return user


def create_access_token(user: User) -> tuple[str, int]:
    """Return the signed token and its lifetime in seconds."""
    expires_in = settings.jwt_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "library_id": user.library_id,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_token(token: str) -> dict:
    """Verify the token as the active mode says and return its claims."""
    try:
        if settings.auth_mode == "cognito":
            return _decode_cognito(token)
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired") from exc
    except jwt.PyJWKClientConnectionError as exc:
        raise AuthUnavailableError("Could not reach the identity provider") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid token") from exc


def resolve_user(db: Dynamo, claims: dict) -> User | None:
    """The user a verified token belongs to, or `None` if it no longer exists."""
    sub = claims.get("sub")
    if not isinstance(sub, str):
        return None
    repo = UserRepository(db)
    if settings.auth_mode == "cognito":
        return repo.get_by_cognito_sub(sub)
    return repo.get(int(sub)) if sub.isdigit() else None


@lru_cache(maxsize=None)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    """One client per JWKS URL and per process, so the key set is fetched once and not
    on every request."""
    return jwt.PyJWKClient(
        url, cache_keys=True, lifespan=_JWKS_LIFESPAN_SECONDS, timeout=_JWKS_TIMEOUT_SECONDS
    )


def _decode_cognito(token: str) -> dict:
    """An access token of our User Pool, issued for our app client.

    Cognito's access token has no `aud`: the app client travels in `client_id`, so
    audience verification is off and `client_id` is checked by hand. The id token does
    have `aud`, and it is rejected by `token_use`: it identifies, it does not authorize.
    """
    signing_key = _jwks_client(settings.cognito_jwks_url).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=_COGNITO_ALGORITHMS,
        issuer=settings.cognito_issuer,
        options={
            "verify_aud": False,
            "require": ["exp", "iss", "sub", "token_use", "client_id"],
        },
    )
    if claims["token_use"] != "access":
        raise jwt.InvalidTokenError("Not an access token")
    if claims["client_id"] != settings.cognito_app_client_id:
        raise jwt.InvalidTokenError("Token issued for another app client")
    return claims
