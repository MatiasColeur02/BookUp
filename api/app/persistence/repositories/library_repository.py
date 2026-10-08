from __future__ import annotations

import dataclasses
from typing import Any

from ..dynamo import Dynamo
from ..entities import Library
from ..errors import ConditionFailedError
from .. import keys
from . import _items, _support as s

_FIELDS = {f.name for f in dataclasses.fields(Library)} - {"id"}


class LibraryRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    @staticmethod
    def _entity(item: dict) -> Library:
        return s.from_item(Library, item)

    def list_all(self) -> list[Library]:
        items = s.query_all(
            self.db,
            IndexName=keys.GSI1,
            KeyConditionExpression="GSI1PK = :list",
            ExpressionAttributeValues={":list": keys.LIST_LIBRARIES},
        )
        return [self._entity(i) for i in items]

    def get(self, library_id: int) -> Library | None:
        item = s.get_item(self.db, keys.library_pk(library_id))
        return self._entity(item) if item else None

    def get_many(self, library_ids: list[int]) -> list[Library]:
        if not library_ids:
            return []
        found = s.batch_get(self.db, [keys.key(keys.library_pk(i)) for i in library_ids])
        return [self._entity(i) for i in found]

    def create(self, library: Library) -> Library:
        created = dataclasses.replace(library, id=s.next_id(self.db, "library"))
        self.db.table.put_item(
            Item=_items.library_item(created),
            ConditionExpression="attribute_not_exists(PK)",
        )
        return created

    def update(self, library_id: int, **changes: Any) -> Library:
        """Actualización parcial. Un valor `None` borra el atributo.

        Renombrar la sede o cambiarle la ciudad reescribe `library_name`/`library_city`
        en cada ejemplar (ROADMAP §3.1): es lo que deja a la disponibilidad y al filtro
        por ciudad leer sin ir a buscar la sede.
        """
        unknown = set(changes) - _FIELDS
        if unknown:
            raise TypeError(f"Unknown Library fields: {sorted(unknown)}")
        current = self.get(library_id)
        if current is None:
            raise ConditionFailedError(f"Library {library_id} does not exist")
        if not changes:
            return current

        updated = dataclasses.replace(current, **changes)
        set_ = {k: v for k, v in changes.items() if v is not None}
        if "name" in changes:
            set_[keys.GSI1_SK] = keys.library(library_id, updated.name)[keys.GSI1_SK]
        s.run_transaction(
            self.db,
            [
                s.tx_update(
                    keys.key(keys.library_pk(library_id)),
                    set_=set_,
                    remove=[k for k, v in changes.items() if v is None],
                    condition="attribute_exists(#pk)",
                    names={"#pk": keys.PK},
                )
            ],
            failed_error=f"Library {library_id} does not exist",
        )

        if "name" in changes or "city" in changes:
            copies = s.query_all(
                self.db,
                IndexName=keys.GSI3,
                KeyConditionExpression="GSI3PK = :lib AND begins_with(GSI3SK, :copy)",
                ExpressionAttributeValues={
                    ":lib": keys.library_pk(library_id),
                    ":copy": keys.library_copies_prefix(),
                },
            )
            s.cascade_set(
                self.db,
                s.index_keys(copies),
                {"library_name": updated.name, "library_city": updated.city},
            )
        return updated

    def delete(self, library: Library) -> None:
        self.db.table.delete_item(Key=keys.key(keys.library_pk(library.id)))

    def has_physical_books(self, library_id: int) -> bool:
        return s.exists_any(
            self.db,
            IndexName=keys.GSI3,
            KeyConditionExpression="GSI3PK = :lib AND begins_with(GSI3SK, :copy)",
            ExpressionAttributeValues={
                ":lib": keys.library_pk(library_id),
                ":copy": keys.library_copies_prefix(),
            },
        )
