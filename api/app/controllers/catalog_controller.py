from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import catalog_service
from . import schemas
from .dependencies import require_roles

router = APIRouter(prefix="/books", tags=["catalog"])

require_staff = require_roles(UserRole.librarian, UserRole.sysadmin)


@router.get("", response_model=list[schemas.BookOut])
def list_books(db: Session = Depends(get_db)):
    return catalog_service.list_books(db)


@router.post("", response_model=schemas.BookOut, status_code=201)
def create_book(
    payload: schemas.BookCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return catalog_service.create_book(db, **payload.model_dump())


# Declared before `/{isbn}` so FastAPI does not match "search" as an ISBN.
@router.get("/search", response_model=list[schemas.BookOut])
def search_books(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return catalog_service.search_books(db, q)


@router.get("/{isbn}", response_model=schemas.BookOut)
def get_book(isbn: str, db: Session = Depends(get_db)):
    return catalog_service.get_book(db, isbn)


@router.patch("/{isbn}", response_model=schemas.BookOut)
def update_book(
    isbn: str,
    payload: schemas.BookUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return catalog_service.update_book(db, isbn, **payload.model_dump(exclude_unset=True))


@router.delete("/{isbn}", status_code=204)
def delete_book(
    isbn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    catalog_service.delete_book(db, isbn)


@router.get("/{isbn}/availability", response_model=schemas.BookAvailability)
def get_availability(isbn: str, db: Session = Depends(get_db)):
    book, rows = catalog_service.get_availability(db, isbn)
    libraries = [
        schemas.LibraryAvailability(
            library=library,
            available_copies=len(physical_books),
            physical_book_id=physical_books[0].id,
        )
        for library, physical_books in rows
    ]
    return schemas.BookAvailability(book=book, libraries=libraries)
