from __future__ import annotations

import dataclasses
from typing import Any

from ..dynamo import Dynamo
from ..entities import User
from ..errors import ConditionFailedError
from .. import keys
from . import _support as s

_FIELDS = {f.name for f in dataclasses.fields(User)} - {"id"}
_NEW = "attribute_not_exists(PK)"


class UserRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    @staticmethod
    def _entity(item: dict) -> User:
        return s.from_item(User, item)

    def list_all(self) -> list[User]:
        items = s.query_all(
            self.db,
            IndexName=keys.GSI1,
            KeyConditionExpression="GSI1PK = :list",
            ExpressionAttributeValues={":list": keys.LIST_USERS},
        )
        return [self._entity(i) for i in items]

    def get(self, user_id: int) -> User | None:
        item = s.get_item(self.db, keys.user_pk(user_id))
        return self._entity(item) if item else None

    def get_by_email(self, email: str) -> User | None:
        """Login: el alias `USEREMAIL#<email>` apunta al usuario, y los dos GetItem son
        lecturas fuertes — un usuario recién creado puede loguearse enseguida."""
        alias = s.get_item(self.db, keys.user_email(email)[keys.PK])
        return self.get(int(alias["user_id"])) if alias else None

    def create(self, user: User) -> User:
        """Alta con unicidad de email, en una transacción con el alias."""
        created = dataclasses.replace(user, id=s.next_id(self.db, "user"))
        s.run_transaction(
            self.db,
            [
                s.tx_put({**keys.user_email(created.email), "user_id": created.id}, condition=_NEW),
                s.tx_put(
                    {**keys.user(created.id, created.name), **s.to_item(created)},
                    condition=_NEW,
                ),
            ],
            exists_error=f"User with email {created.email} already exists",
        )
        return created

    def update(self, user_id: int, **changes: Any) -> User:
        """Actualización parcial. Un valor `None` borra el atributo (`library_id`).

        Cambiar `email` mueve el alias en la misma transacción: si no, el email viejo
        seguiría bloqueado para siempre y el nuevo no podría loguear.
        """
        unknown = set(changes) - _FIELDS
        if unknown:
            raise TypeError(f"Unknown User fields: {sorted(unknown)}")
        current = self.get(user_id)
        if current is None:
            raise ConditionFailedError(f"User {user_id} does not exist")
        if not changes:
            return current

        updated = dataclasses.replace(current, **changes)
        set_ = {k: v for k, v in changes.items() if v is not None}
        if "name" in changes:
            set_[keys.GSI1_SK] = keys.user(user_id, updated.name)[keys.GSI1_SK]

        ops = [
            s.tx_update(
                keys.key(keys.user_pk(user_id)),
                set_=set_,
                remove=[k for k, v in changes.items() if v is None],
                # Sigue siendo el usuario que leímos (mismo email): protege al alias.
                condition="#e = :email",
                names={"#e": "email"},
                values={":email": current.email},
            )
        ]
        if updated.email != current.email:
            ops += [
                s.tx_delete(keys.key(keys.user_email(current.email)[keys.PK])),
                s.tx_put({**keys.user_email(updated.email), "user_id": user_id}, condition=_NEW),
            ]
        s.run_transaction(
            self.db,
            ops,
            exists_error=f"User with email {updated.email} already exists",
            failed_error=f"User {user_id} changed while it was being updated",
        )
        return updated

    def delete(self, user: User) -> None:
        """Baja del usuario **y** de su alias, para que el email se pueda reusar."""
        s.run_transaction(
            self.db,
            [
                s.tx_delete(keys.key(keys.user_pk(user.id))),
                s.tx_delete(keys.key(keys.user_email(user.email)[keys.PK])),
            ],
        )
