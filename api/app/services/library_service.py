from sqlalchemy.orm import Session

from ..persistence.models import Library
from ..persistence.repositories import LibraryRepository


def list_libraries(db: Session) -> list[Library]:
    return LibraryRepository(db).list_all()


def create_library(
    db: Session,
    *,
    name: str,
    address: str,
    state: str,
    city: str,
    hours: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    website: str | None = None,
) -> Library:
    library = LibraryRepository(db).create(
        Library(
            name=name,
            address=address,
            state=state,
            city=city,
            hours=hours,
            phone=phone,
            email=email,
            website=website,
        )
    )
    db.commit()
    db.refresh(library)
    return library
