from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import library_service
from . import schemas
from .dependencies import get_current_user, require_roles

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("", response_model=list[schemas.LibraryOut])
def list_libraries(db: Session = Depends(get_db)):
    return library_service.list_libraries(db)


@router.post("", response_model=schemas.LibraryOut, status_code=201)
def create_library(
    payload: schemas.LibraryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.sysadmin)),
):
    return library_service.create_library(db, **payload.model_dump())


@router.get("/{library_id}", response_model=schemas.LibraryOut)
def get_library(library_id: int, db: Session = Depends(get_db)):
    return library_service.get_library(db, library_id)


@router.patch("/{library_id}", response_model=schemas.LibraryOut)
def update_library(
    library_id: int,
    payload: schemas.LibraryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return library_service.update_library(
        db, library_id, editor=current_user, **payload.model_dump(exclude_unset=True)
    )


@router.delete("/{library_id}", status_code=204)
def delete_library(
    library_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.sysadmin)),
):
    library_service.delete_library(db, library_id)
