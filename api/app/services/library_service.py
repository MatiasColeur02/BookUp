from sqlalchemy.orm import Session

from ..persistence.models import Library, User, UserRole
from ..persistence.repositories import LibraryRepository
from .errors import ConflictError, ForbiddenError, NotFoundError


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


def _assert_can_manage(editor: User, library_id: int) -> None:
    """A sysadmin manages every branch; a librarian only their own."""
    if editor.role is UserRole.sysadmin:
        return
    if editor.role is UserRole.librarian and editor.library_id == library_id:
        return
    raise ForbiddenError(f"You are not allowed to manage library {library_id}")


def update_library(
    db: Session,
    library_id: int,
    *,
    editor: User,
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
    _assert_can_manage(editor, library_id)

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
