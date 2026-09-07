from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import genre_service
from . import schemas
from .dependencies import require_roles

router = APIRouter(prefix="/genres", tags=["genres"])

require_staff = require_roles(UserRole.librarian, UserRole.sysadmin)


@router.get("", response_model=list[schemas.GenreOut])
def list_genres(db: Session = Depends(get_db)):
    return genre_service.list_genres(db)


@router.post("", response_model=schemas.GenreOut, status_code=201)
def create_genre(
    payload: schemas.GenreCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return genre_service.create_genre(db, **payload.model_dump())


@router.get("/{genre_id}", response_model=schemas.GenreOut)
def get_genre(genre_id: int, db: Session = Depends(get_db)):
    return genre_service.get_genre(db, genre_id)


@router.patch("/{genre_id}", response_model=schemas.GenreOut)
def update_genre(
    genre_id: int,
    payload: schemas.GenreUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return genre_service.update_genre(db, genre_id, **payload.model_dump(exclude_unset=True))


@router.delete("/{genre_id}", status_code=204)
def delete_genre(
    genre_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    genre_service.delete_genre(db, genre_id)
