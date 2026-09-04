from sqlalchemy.orm import Session

from ..persistence.models import Library
from ..persistence.repositories import LibraryRepository


def list_libraries(db: Session) -> list[Library]:
    return LibraryRepository(db).list_all()


def create_library(db: Session, *, name: str, city: str, address: str | None) -> Library:
    library = LibraryRepository(db).create(Library(name=name, city=city, address=address))
    db.commit()
    db.refresh(library)
    return library
