from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import user_service
from . import schemas
from .dependencies import require_roles, require_self_or_sysadmin

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    return user_service.create_user(db, **payload.model_dump())


@router.post("/staff", response_model=schemas.UserOut, status_code=201)
def create_staff_user(
    payload: schemas.UserStaffCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.sysadmin)),
):
    return user_service.create_user(db, **payload.model_dump())


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.sysadmin)),
):
    return user_service.list_users(db)


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_self_or_sysadmin),
):
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_sysadmin),
):
    return user_service.update_user(
        db, user_id, editor=current_user, **payload.model_dump(exclude_unset=True)
    )


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_self_or_sysadmin),
):
    user_service.delete_user(db, user_id)
