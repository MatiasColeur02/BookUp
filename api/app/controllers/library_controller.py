from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..services import library_service
from . import schemas

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("", response_model=list[schemas.LibraryOut])
def list_libraries(db: Session = Depends(get_db)):
    return library_service.list_libraries(db)


@router.post("", response_model=schemas.LibraryOut, status_code=201)
def create_library(payload: schemas.LibraryCreate, db: Session = Depends(get_db)):
    return library_service.create_library(db, **payload.model_dump())
