"""FastAPI dependencies that resolve and authorize the caller.

Role-only rules live here (`require_roles`). Rules that depend on the data of
the resource being touched — "a librarian may only act on their own branch" —
live in the services, next to the entity they have to load anyway.
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..persistence.repositories import UserRepository
from ..services import auth_service
from ..services.errors import ForbiddenError, UnauthorizedError

# auto_error=False so a missing header raises our own UnauthorizedError and gets
# the same JSON error shape as the rest of the API.
_bearer = HTTPBearer(auto_error=False, description="JWT emitido por `POST /auth/login`")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")

    payload = auth_service.decode_token(credentials.credentials)
    user = UserRepository(db).get(int(payload["sub"]))
    if user is None:
        # Valid signature, but the user was deleted after the token was issued.
        raise UnauthorizedError("Invalid token")
    return user


def require_roles(*roles: UserRole):
    """Dependency factory: only these roles may call the endpoint."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise ForbiddenError(f"Requires one of: {', '.join(r.value for r in roles)}")
        return current_user

    return dependency


def require_self_or_sysadmin(
    user_id: int, current_user: User = Depends(get_current_user)
) -> User:
    """For `/users/{user_id}`: the user themselves, or a sysadmin."""
    if current_user.role is not UserRole.sysadmin and current_user.id != user_id:
        raise ForbiddenError("You can only access your own user")
    return current_user
