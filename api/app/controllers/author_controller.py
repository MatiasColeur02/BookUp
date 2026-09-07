from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import author_service
from . import schemas
from .dependencies import require_roles

router = APIRouter(prefix="/authors", tags=["authors"])

require_staff = require_roles(UserRole.librarian, UserRole.sysadmin)


@router.get("", response_model=list[schemas.AuthorOut])
def list_authors(db: Session = Depends(get_db)):
    return author_service.list_authors(db)


@router.post("", response_model=schemas.AuthorOut, status_code=201)
def create_author(
    payload: schemas.AuthorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return author_service.create_author(db, **payload.model_dump())


@router.get("/{author_id}", response_model=schemas.AuthorOut)
def get_author(author_id: int, db: Session = Depends(get_db)):
    return author_service.get_author(db, author_id)


@router.patch("/{author_id}", response_model=schemas.AuthorOut)
def update_author(
    author_id: int,
    payload: schemas.AuthorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return author_service.update_author(db, author_id, **payload.model_dump(exclude_unset=True))


@router.delete("/{author_id}", status_code=204)
def delete_author(
    author_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    author_service.delete_author(db, author_id)
