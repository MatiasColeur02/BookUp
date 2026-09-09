from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import ratelimit
from ..persistence.database import get_db
from ..persistence.models import User
from ..services import auth_service
from ..services.errors import UnauthorizedError
from . import schemas
from .dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(request: Request, payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    # El freno por IP va antes de tocar la base; el de la cuenta, solo sobre los intentos
    # fallidos, para que nadie pueda bloquear a otro usuario a fuerza de errarle la
    # contraseña. Ver `ratelimit.failed_login`.
    ratelimit.login_attempt(request)
    try:
        user = auth_service.authenticate(db, email=payload.email, password=payload.password)
    except UnauthorizedError:
        ratelimit.failed_login(payload.email)
        raise
    token, expires_in = auth_service.create_access_token(user)
    return schemas.TokenOut(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
