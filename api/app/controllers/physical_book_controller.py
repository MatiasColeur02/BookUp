from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import PhysicalBookStatus, User, UserRole
from ..services import physical_book_service
from . import schemas
from .dependencies import require_roles

router = APIRouter(prefix="/physical-books", tags=["physical_books"])

require_staff = require_roles(UserRole.librarian, UserRole.sysadmin)


@router.get("", response_model=list[schemas.PhysicalBookOut])
def list_physical_books(
    isbn: str | None = None,
    library_id: int | None = None,
    status: PhysicalBookStatus | None = None,
    db: Session = Depends(get_db),
):
    return physical_book_service.list_physical_books(
        db, isbn=isbn, library_id=library_id, status=status
    )


@router.post("", response_model=schemas.PhysicalBookOut, status_code=201)
def create_physical_book(
    payload: schemas.PhysicalBookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return physical_book_service.create_physical_book(
        db, editor=current_user, **payload.model_dump()
    )


@router.get("/{physical_book_id}", response_model=schemas.PhysicalBookOut)
def get_physical_book(physical_book_id: int, db: Session = Depends(get_db)):
    return physical_book_service.get_physical_book(db, physical_book_id)


@router.patch("/{physical_book_id}/status", response_model=schemas.PhysicalBookOut)
def update_status(
    physical_book_id: int,
    payload: schemas.PhysicalBookStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return physical_book_service.update_status(
        db, physical_book_id, status=payload.status, editor=current_user
    )


@router.delete("/{physical_book_id}", status_code=204)
def delete_physical_book(
    physical_book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    physical_book_service.delete_physical_book(db, physical_book_id, editor=current_user)
