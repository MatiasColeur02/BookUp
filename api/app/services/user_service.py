from sqlalchemy.orm import Session

from ..persistence.models import User, UserRole
from ..persistence.repositories import LibraryRepository, UserRepository
from .auth_service import hash_password
from .errors import ConflictError, ForbiddenError, NotFoundError


def _validate_role_and_library(db: Session, role: UserRole, library_id: int | None) -> None:
    """`library_id` only means something for a librarian: it is the branch they run."""
    if library_id is None:
        return
    if role is not UserRole.librarian:
        raise ConflictError(f"Only a librarian can have a library_id, not a {role.value}")
    if LibraryRepository(db).get(library_id) is None:
        raise NotFoundError(f"Library {library_id} not found")


def list_users(db: Session) -> list[User]:
    return UserRepository(db).list_all()


def get_user(db: Session, user_id: int) -> User:
    user = UserRepository(db).get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return user


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    name: str,
    language: str = "es",
    role: UserRole = UserRole.customer,
    library_id: int | None = None,
) -> User:
    """Create a user. Self-registration always lands on the `customer` default;
    only `POST /users/staff` (sysadmin-only) passes a different `role`."""
    repo = UserRepository(db)
    if repo.get_by_email(email) is not None:
        raise ConflictError(f"User with email {email} already exists")

    _validate_role_and_library(db, role, library_id)

    user = repo.create(
        User(
            email=email,
            password_hash=hash_password(password),
            name=name,
            language=language,
            role=role,
            library_id=library_id,
        )
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: int,
    *,
    editor: User,
    name: str | None = None,
    language: str | None = None,
    password: str | None = None,
    role: UserRole | None = None,
    library_id: int | None = None,
) -> User:
    user = get_user(db, user_id)

    if (role is not None or library_id is not None) and editor.role is not UserRole.sysadmin:
        raise ForbiddenError("Only a sysadmin can change role or library_id")

    if name is not None:
        user.name = name
    if language is not None:
        user.language = language
    if password is not None:
        user.password_hash = hash_password(password)
    if role is not None:
        user.role = role
        # Demoting a librarian drops the branch they used to run, so the caller
        # doesn't have to null a field that a partial update can't null.
        if role is not UserRole.librarian and library_id is None:
            user.library_id = None
    if library_id is not None:
        user.library_id = library_id

    _validate_role_and_library(db, user.role, user.library_id)

    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> None:
    repo = UserRepository(db)
    user = repo.get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")

    repo.delete(user)
    db.commit()
