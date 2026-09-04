from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import Copy, CopyStatus, Library


class CopyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, copy_id: int) -> Copy | None:
        return self.db.get(Copy, copy_id)

    def available_by_book(self, book_id: int) -> list[tuple[Library, list[Copy]]]:
        """Available copies of a book, grouped by the library that holds them."""
        stmt = (
            select(Copy)
            .options(joinedload(Copy.library))
            .where(Copy.book_id == book_id, Copy.status == CopyStatus.available)
        )
        copies = list(self.db.scalars(stmt).unique().all())

        grouped: dict[int, tuple[Library, list[Copy]]] = {}
        for copy in copies:
            _, bucket = grouped.setdefault(copy.library_id, (copy.library, []))
            bucket.append(copy)
        return list(grouped.values())
