from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[User]:
        return list(self.db.scalars(select(User)).all())

    def get(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.flush()
