from sqlalchemy.orm import Session

from ..persistence.models import PhysicalBook, PhysicalBookStatus, User, UserRole
from ..persistence.repositories import (
    BookRepository,
    LibraryRepository,
    PhysicalBookRepository,
)
from .errors import ConflictError, ForbiddenError, NotFoundError

# Statuses a human may set directly. `reserved` and `loaned` belong to the
# reservation flow (`POST /reservations`, `PATCH /reservations/{id}/pickup`).
MANUAL_STATUSES = (PhysicalBookStatus.available, PhysicalBookStatus.lost)


def _assert_can_manage(editor: User, library_id: int) -> None:
    """A sysadmin manages every branch's copies; a librarian only their own."""
    if editor.role is UserRole.sysadmin:
        return
    if editor.role is UserRole.librarian and editor.library_id == library_id:
        return
    raise ForbiddenError(f"You are not allowed to manage copies of library {library_id}")


def list_physical_books(
    db: Session,
    *,
    isbn: str | None = None,
    library_id: int | None = None,
    status: PhysicalBookStatus | None = None,
) -> list[PhysicalBook]:
    return PhysicalBookRepository(db).list(isbn=isbn, library_id=library_id, status=status)


def get_physical_book(db: Session, physical_book_id: int) -> PhysicalBook:
    physical_book = PhysicalBookRepository(db).get(physical_book_id)
    if physical_book is None:
        raise NotFoundError(f"Physical book {physical_book_id} not found")
    return physical_book


def create_physical_book(
    db: Session, *, isbn: str, library_id: int, editor: User
) -> PhysicalBook:
    _assert_can_manage(editor, library_id)

    if BookRepository(db).get(isbn) is None:
        raise NotFoundError(f"Book {isbn} not found")
    if LibraryRepository(db).get(library_id) is None:
        raise NotFoundError(f"Library {library_id} not found")

    physical_book = PhysicalBookRepository(db).create(
        PhysicalBook(isbn=isbn, library_id=library_id, status=PhysicalBookStatus.available)
    )
    db.commit()
    db.refresh(physical_book)
    return physical_book


def update_status(
    db: Session, physical_book_id: int, *, status: PhysicalBookStatus, editor: User
) -> PhysicalBook:
    physical_book = get_physical_book(db, physical_book_id)
    _assert_can_manage(editor, physical_book.library_id)

    if status not in MANUAL_STATUSES:
        raise ConflictError(f"Status {status.value} is driven by the reservation flow")
    # Flipping a copy that a reservation is pointing at would leave that
    # reservation dangling; releasing it is the reservation flow's job.
    if physical_book.status not in MANUAL_STATUSES:
        raise ConflictError(
            f"Physical book {physical_book_id} is {physical_book.status.value}: "
            "resolve its reservation first"
        )

    physical_book.status = status
    db.commit()
    db.refresh(physical_book)
    return physical_book


def delete_physical_book(db: Session, physical_book_id: int, *, editor: User) -> None:
    repo = PhysicalBookRepository(db)
    physical_book = repo.get(physical_book_id)
    if physical_book is None:
        raise NotFoundError(f"Physical book {physical_book_id} not found")

    _assert_can_manage(editor, physical_book.library_id)

    if repo.count_reservations(physical_book_id):
        raise ConflictError(f"Physical book {physical_book_id} still has reservations")

    repo.delete(physical_book)
    db.commit()
