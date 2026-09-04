from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Library


class LibraryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Library]:
        return list(self.db.scalars(select(Library)).all())

    def get(self, library_id: int) -> Library | None:
        return self.db.get(Library, library_id)

    def create(self, library: Library) -> Library:
        self.db.add(library)
        self.db.flush()
        return library
