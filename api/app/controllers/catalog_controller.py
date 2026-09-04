from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..services import catalog_service
from . import schemas

router = APIRouter(prefix="/books", tags=["catalog"])


@router.get("/search", response_model=list[schemas.BookOut])
def search_books(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return catalog_service.search_books(db, q)


@router.get("/{book_id}", response_model=schemas.BookOut)
def get_book(book_id: int, db: Session = Depends(get_db)):
    return catalog_service.get_book(db, book_id)


@router.get("/{book_id}/availability", response_model=schemas.BookAvailability)
def get_availability(book_id: int, db: Session = Depends(get_db)):
    book, rows = catalog_service.get_availability(db, book_id)
    libraries = [
        schemas.LibraryAvailability(library=library, available_copies=len(copies), copy_id=copies[0].id)
        for library, copies in rows
    ]
    return schemas.BookAvailability(book=book, libraries=libraries)
