from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Library, PhysicalBook


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

    def delete(self, library: Library) -> None:
        self.db.delete(library)
        self.db.flush()

    def count_physical_books(self, library_id: int) -> int:
        return self.db.scalar(
            select(func.count()).select_from(PhysicalBook).where(
                PhysicalBook.library_id == library_id
            )
        )
