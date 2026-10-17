import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import identity, ratelimit
from ..config import settings
from ..persistence.dynamo import Dynamo, get_db
from ..persistence.entities import User, UserRole
from ..services import user_service
from ..services.auth_service import normalize_email
from ..services.errors import ConflictError
from . import schemas
from .dependencies import require_roles, require_self_or_sysadmin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])
# Solo con `AUTH_MODE=local` (`main.py`): con Cognito el auto-registro es la Hosted UI más
# el trigger Post Confirmation (`app/cognito_triggers.py`).
signup_router = APIRouter(prefix="/users", tags=["users"])


def _cognito() -> bool:
    return settings.auth_mode == "cognito"


@signup_router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(request: Request, payload: schemas.UserCreate, db: Dynamo = Depends(get_db)):
    # `POST /users/staff` no se frena: pide un token de sysadmin, así que ya está acotado.
    ratelimit.signup_attempt(request)
    return user_service.create_user(db, **payload.model_dump())


@router.post("/staff", response_model=schemas.UserOut, status_code=201)
def create_staff_user(
    payload: schemas.UserStaffCreate,
    db: Dynamo = Depends(get_db),
    _: User = Depends(require_roles(UserRole.sysadmin)),
):
    if not _cognito():
        return user_service.create_user(db, **payload.model_dump())
    return _create_staff_in_cognito(db, payload)


def _create_staff_in_cognito(db: Dynamo, payload: schemas.UserStaffCreate) -> User:
    """Primero la cuenta de Cognito (la `password` es la temporal), después el `User`.

    Si el `User` no se puede crear —email ya registrado en la base, sede inexistente, o
    cualquier otra falla—, la cuenta de Cognito se borra: si no, quedaría una cuenta que
    entra a la Hosted UI y recibe 401 para siempre, bloqueando ese email.
    """
    data = payload.model_dump()
    email = normalize_email(data.pop("email"))
    password = data.pop("password")
    try:
        sub = identity.create_user(email=email, name=data["name"], temporary_password=password)
    except identity.UsernameExistsError as exc:
        raise ConflictError(f"User with email {email} already exists") from exc
    except identity.InvalidPasswordError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return user_service.create_user(db, email=email, password=None, cognito_sub=sub, **data)
    except Exception:
        try:
            identity.delete_user(sub)
        except identity.IdentityError:
            # El error que importa es el original; este deja una cuenta huérfana a mano.
            logger.error("could not roll back Cognito account %s after a failed staff creation", sub)
        raise


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    db: Dynamo = Depends(get_db),
    _: User = Depends(require_roles(UserRole.sysadmin)),
):
    return user_service.list_users(db)


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(
    user_id: int,
    db: Dynamo = Depends(get_db),
    _: User = Depends(require_self_or_sysadmin),
):
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Dynamo = Depends(get_db),
    current_user: User = Depends(require_self_or_sysadmin),
):
    changes = payload.model_dump(exclude_unset=True)
    if _cognito() and changes.get("password") is not None:
        # La contraseña la guarda Cognito: se cambia en la Hosted UI («olvidé mi contraseña»).
        raise HTTPException(
            status_code=422,
            detail="The password is managed by the identity provider; change it from the login page",
        )
    return user_service.update_user(db, user_id, editor=current_user, **changes)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Dynamo = Depends(get_db),
    _: User = Depends(require_self_or_sysadmin),
):
    if _cognito():
        # Primero Cognito: si después falla DynamoDB, la persona ya no puede entrar y
        # reintentar el DELETE termina el trabajo. Al revés quedaría una cuenta huérfana que
        # bloquea ese email para siempre.
        user = user_service.get_user(db, user_id)
        identity.delete_user(user.cognito_sub or user.email)
    user_service.delete_user(db, user_id)
