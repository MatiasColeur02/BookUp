import bcrypt
from sqlalchemy.orm import Session

from ..persistence.models import User, UserRole
from ..persistence.repositories import UserRepository
from .errors import ConflictError, NotFoundError


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def list_users(db: Session) -> list[User]:
    return UserRepository(db).list_all()


def get_user(db: Session, user_id: int) -> User:
    user = UserRepository(db).get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return user


def create_user(db: Session, *, email: str, password: str, name: str, language: str = "es") -> User:
    repo = UserRepository(db)
    if repo.get_by_email(email) is not None:
        raise ConflictError(f"User with email {email} already exists")

    user = repo.create(
        User(
            email=email,
            password_hash=_hash_password(password),
            name=name,
            language=language,
            role=UserRole.customer,
        )
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: int,
    *,
    name: str | None = None,
    language: str | None = None,
    password: str | None = None,
) -> User:
    user = get_user(db, user_id)

    if name is not None:
        user.name = name
    if language is not None:
        user.language = language
    if password is not None:
        user.password_hash = _hash_password(password)

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
