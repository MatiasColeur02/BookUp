from sqlalchemy.orm import Session

from ..persistence.models import Library
from ..persistence.repositories import LibraryRepository
from .errors import ConflictError, NotFoundError


def list_libraries(db: Session) -> list[Library]:
    return LibraryRepository(db).list_all()


def get_library(db: Session, library_id: int) -> Library:
    library = LibraryRepository(db).get(library_id)
    if library is None:
        raise NotFoundError(f"Library {library_id} not found")
    return library


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


def update_library(
    db: Session,
    library_id: int,
    *,
    name: str | None = None,
    address: str | None = None,
    state: str | None = None,
    city: str | None = None,
    hours: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    website: str | None = None,
) -> Library:
    library = get_library(db, library_id)

    # Partial update: like `update_user`, a None means "not sent" rather than
    # "set to null", so the optional fields can't be cleared through here.
    for field, value in (
        ("name", name),
        ("address", address),
        ("state", state),
        ("city", city),
        ("hours", hours),
        ("phone", phone),
        ("email", email),
        ("website", website),
    ):
        if value is not None:
            setattr(library, field, value)

    db.commit()
    db.refresh(library)
    return library


def delete_library(db: Session, library_id: int) -> None:
    repo = LibraryRepository(db)
    library = repo.get(library_id)
    if library is None:
        raise NotFoundError(f"Library {library_id} not found")

    # Physical copies reference the library; deleting it would orphan them.
    if repo.count_physical_books(library_id):
        raise ConflictError(f"Library {library_id} still has physical books")

    repo.delete(library)
    db.commit()
