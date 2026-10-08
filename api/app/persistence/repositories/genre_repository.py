from __future__ import annotations

from ..dynamo import Dynamo
from ..entities import Genre
from ..errors import AlreadyExistsError, ConditionFailedError
from .. import keys
from . import _items, _support as s

_NEW = "attribute_not_exists(PK)"
_EXISTS = "attribute_exists(PK)"


class GenreRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    @staticmethod
    def _entity(item: dict) -> Genre:
        return s.from_item(Genre, item)

    def list_all(self) -> list[Genre]:
        items = s.query_all(
            self.db,
            IndexName=keys.GSI1,
            KeyConditionExpression="GSI1PK = :list",
            ExpressionAttributeValues={":list": keys.LIST_GENRES},
        )
        return [self._entity(i) for i in items]

    def get(self, genre_id: int) -> Genre | None:
        item = s.get_item(self.db, keys.genre_pk(genre_id))
        return self._entity(item) if item else None

    def get_by_name(self, name: str) -> Genre | None:
        """Por el ítem alias `GENRENAME#<name>`: un GetItem, sin índice."""
        alias = s.get_item(self.db, keys.genre_name(name)[keys.PK])
        return self.get(int(alias["genre_id"])) if alias else None

    def get_many(self, genre_ids: list[int]) -> list[Genre]:
        if not genre_ids:
            return []
        found = s.batch_get(self.db, [keys.key(keys.genre_pk(i)) for i in genre_ids])
        return [self._entity(i) for i in found]

    def create(self, genre: Genre) -> Genre:
        """Alta con unicidad de nombre: el alias y el género entran en la misma
        transacción, y el alias lleva el `attribute_not_exists` que hacía el UNIQUE."""
        created = Genre(name=genre.name, id=s.next_id(self.db, "genre"))
        s.run_transaction(
            self.db,
            [
                s.tx_put(_items.genre_alias_item(created.name, created.id), condition=_NEW),
                s.tx_put(_items.genre_item(created), condition=_NEW),
            ],
            exists_error=f"Genre {created.name!r} already exists",
        )
        return created

    def update(self, genre_id: int, *, name: str) -> Genre:
        """Renombra: mueve el alias de unicidad, actualiza el género y cascadea el nombre
        a los libros. El alias nuevo y el género van en una transacción, así que un nombre
        repetido falla *antes* de tocar ningún libro."""
        current = self.get(genre_id)
        if current is None:
            raise ConditionFailedError(f"Genre {genre_id} does not exist")

        if name != current.name:
            s.run_transaction(
                self.db,
                [
                    s.tx_delete(keys.key(keys.genre_name(current.name)[keys.PK])),
                    s.tx_put(_items.genre_alias_item(name, genre_id), condition=_NEW),
                    s.tx_update(
                        keys.key(keys.genre_pk(genre_id)),
                        set_={"name": name, keys.GSI1_SK: keys.genre(genre_id, name)[keys.GSI1_SK]},
                        # El nombre que leímos sigue siendo el vigente: sin esto, dos
                        # renombres simultáneos dejarían un alias huérfano.
                        condition="#n = :old",
                        names={"#n": "name"},
                        values={":old": current.name},
                    ),
                ],
                exists_error=f"Genre {name!r} already exists",
                failed_error=f"Genre {genre_id} changed while it was being renamed",
            )

        links = s.query_all(
            self.db,
            IndexName=keys.GSI2,
            KeyConditionExpression="GSI2PK = :genre",
            ExpressionAttributeValues={":genre": keys.genre_pk(genre_id)},
        )
        s.cascade_set(self.db, s.index_keys(links), {"genre_name": name})
        return Genre(id=genre_id, name=name)

    def delete(self, genre: Genre) -> None:
        s.run_transaction(
            self.db,
            [
                s.tx_delete(keys.key(keys.genre_pk(genre.id))),
                s.tx_delete(keys.key(keys.genre_name(genre.name)[keys.PK])),
            ],
        )

    def has_books(self, genre_id: int) -> bool:
        return s.exists_any(
            self.db,
            IndexName=keys.GSI2,
            KeyConditionExpression="GSI2PK = :genre",
            ExpressionAttributeValues={":genre": keys.genre_pk(genre_id)},
        )
