from __future__ import annotations

from ..dynamo import Dynamo
from ..entities import Author
from ..errors import ConditionFailedError
from .. import keys
from . import _items, _support as s

_EXISTS = "attribute_exists(#pk)"
_PK = {"#pk": keys.PK}


class AuthorRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    @staticmethod
    def _entity(item: dict) -> Author:
        return s.from_item(Author, item)

    def list_all(self) -> list[Author]:
        """Todos los autores, ya ordenados por nombre: el orden lo da el índice."""
        items = s.query_all(
            self.db,
            IndexName=keys.GSI1,
            KeyConditionExpression="GSI1PK = :list",
            ExpressionAttributeValues={":list": keys.LIST_AUTHORS},
        )
        return [self._entity(i) for i in items]

    def get(self, author_id: int) -> Author | None:
        item = s.get_item(self.db, keys.author_pk(author_id))
        return self._entity(item) if item else None

    def get_many(self, author_ids: list[int]) -> list[Author]:
        if not author_ids:
            return []
        found = s.batch_get(self.db, [keys.key(keys.author_pk(i)) for i in author_ids])
        return [self._entity(i) for i in found]

    def create(self, author: Author) -> Author:
        created = Author(name=author.name, id=s.next_id(self.db, "author"))
        self.db.table.put_item(
            Item=_items.author_item(created),
            ConditionExpression="attribute_not_exists(PK)",
        )
        return created

    def update(self, author_id: int, *, name: str) -> Author:
        """Renombra al autor y propaga el nombre a los ítems `BOOK#<isbn>/AUTHOR#<id>`.

        Es el precio de desnormalizar (ROADMAP §4.3). Primero se escribe el nombre
        canónico y después se cascadea: si la cascada se corta, repetir el update la
        termina, y el ítem `AUTHOR#` ya dice la verdad.
        """
        pk = keys.author_pk(author_id)
        try:
            self.db.table.update_item(
                Key=keys.key(pk),
                UpdateExpression="SET #n = :name, GSI1SK = :sort",
                ConditionExpression=_EXISTS,
                ExpressionAttributeNames={"#n": "name", **_PK},
                ExpressionAttributeValues={
                    ":name": name,
                    ":sort": keys.author(author_id, name)[keys.GSI1_SK],
                },
            )
        except self.db.client.exceptions.ConditionalCheckFailedException as exc:
            raise ConditionFailedError(f"Author {author_id} does not exist") from exc

        links = s.query_all(
            self.db,
            IndexName=keys.GSI2,
            KeyConditionExpression="GSI2PK = :author",
            ExpressionAttributeValues={":author": pk},
        )
        s.cascade_set(
            self.db,
            [keys.key(i[keys.PK], i[keys.SK]) for i in links],
            {"author_name": name},
        )
        return Author(id=author_id, name=name)

    def delete(self, author: Author) -> None:
        self.db.table.delete_item(Key=keys.key(keys.author_pk(author.id)))

    def has_books(self, author_id: int) -> bool:
        return s.exists_any(
            self.db,
            IndexName=keys.GSI2,
            KeyConditionExpression="GSI2PK = :author",
            ExpressionAttributeValues={":author": keys.author_pk(author_id)},
        )
