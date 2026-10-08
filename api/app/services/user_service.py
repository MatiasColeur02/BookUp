from ..persistence.dynamo import Dynamo
from ..persistence.entities import User, UserRole
from ..persistence.errors import AlreadyExistsError, ConditionFailedError
from ..persistence.repositories import LibraryRepository, UserRepository
from .auth_service import hash_password
from .errors import ConflictError, ForbiddenError, NotFoundError


def _validate_role_and_library(db: Dynamo, role: UserRole, library_id: int | None) -> None:
    """`library_id` only means something for a librarian: it is the branch they run."""
    if library_id is None:
        return
    if role is not UserRole.librarian:
        raise ConflictError(f"Only a librarian can have a library_id, not a {role.value}")
    if LibraryRepository(db).get(library_id) is None:
        raise NotFoundError(f"Library {library_id} not found")


def list_users(db: Dynamo) -> list[User]:
    return UserRepository(db).list_all()


def get_user(db: Dynamo, user_id: int) -> User:
    user = UserRepository(db).get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return user


def create_user(
    db: Dynamo,
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

    try:
        return repo.create(
            User(
                email=email,
                password_hash=hash_password(password),
                name=name,
                language=language,
                role=role,
                library_id=library_id,
            )
        )
    except AlreadyExistsError as exc:  # someone registered the same email meanwhile
        raise ConflictError(f"User with email {email} already exists") from exc


def update_user(
    db: Dynamo,
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

    changes: dict = {}
    if name is not None:
        changes["name"] = name
    if language is not None:
        changes["language"] = language
    if password is not None:
        changes["password_hash"] = hash_password(password)

    new_role = role if role is not None else user.role
    new_library_id = user.library_id
    if role is not None:
        changes["role"] = role
        # Demoting a librarian drops the branch they used to run, so the caller
        # doesn't have to null a field that a partial update can't null.
        if role is not UserRole.librarian and library_id is None:
            new_library_id = None
    if library_id is not None:
        new_library_id = library_id
    _validate_role_and_library(db, new_role, new_library_id)
    if new_library_id != user.library_id:
        changes["library_id"] = new_library_id  # None removes the attribute

    if not changes:
        return user
    try:
        return UserRepository(db).update(user_id, **changes)
    except ConditionFailedError as exc:
        raise NotFoundError(f"User {user_id} not found") from exc


def delete_user(db: Dynamo, user_id: int) -> None:
    repo = UserRepository(db)
    user = repo.get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    repo.delete(user)
