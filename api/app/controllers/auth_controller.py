from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User
from ..services import auth_service
from . import schemas
from .dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, email=payload.email, password=payload.password)
    token, expires_in = auth_service.create_access_token(user)
    return schemas.TokenOut(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
