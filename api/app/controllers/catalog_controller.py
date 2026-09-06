from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..services import catalog_service
from . import schemas

router = APIRouter(prefix="/books", tags=["catalog"])


@router.get("", response_model=list[schemas.BookOut])
def list_books(db: Session = Depends(get_db)):
    return catalog_service.list_books(db)


@router.get("/search", response_model=list[schemas.BookOut])
def search_books(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return catalog_service.search_books(db, q)


@router.get("/{isbn}", response_model=schemas.BookOut)
def get_book(isbn: str, db: Session = Depends(get_db)):
    return catalog_service.get_book(db, isbn)


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
