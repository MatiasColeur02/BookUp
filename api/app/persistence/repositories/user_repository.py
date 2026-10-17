from __future__ import annotations

import dataclasses
from typing import Any

from ..dynamo import Dynamo
from ..entities import User
from ..errors import ConditionFailedError
from .. import keys
from . import _items, _support as s

# `cognito_sub` no se cambia con `update`: va junto con su alias, ver `set_cognito_sub`.
_FIELDS = {f.name for f in dataclasses.fields(User)} - {"id", "cognito_sub"}
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

    def get_by_cognito_sub(self, sub: str) -> User | None:
        """El `sub` de un access token de Cognito → el usuario, por su alias `USERSUB#<sub>`.
        Lecturas fuertes, igual que `get_by_email`."""
        alias = s.get_item(self.db, keys.user_sub(sub)[keys.PK])
        return self.get(int(alias["user_id"])) if alias else None

    def create(self, user: User) -> User:
        """Alta con unicidad de email (y de `cognito_sub`, si viene), en una transacción
        con los alias."""
        created = dataclasses.replace(user, id=s.next_id(self.db, "user"))
        ops = [
            s.tx_put(_items.user_alias_item(created.email, created.id), condition=_NEW),
            s.tx_put(_items.user_item(created), condition=_NEW),
        ]
        exists_error = f"User with email {created.email} already exists"
        if created.cognito_sub is not None:
            ops.append(
                s.tx_put(_items.user_sub_alias_item(created.cognito_sub, created.id), condition=_NEW)
            )
            exists_error = (
                f"User with email {created.email} or Cognito sub {created.cognito_sub} already exists"
            )
        s.run_transaction(self.db, ops, exists_error=exists_error)
        return created

    def set_cognito_sub(self, user_id: int, sub: str) -> User:
        """Vincula un usuario existente con su `sub` de Cognito (lo usa `seed_cognito`).

        Solo la primera vez: volver a vincular el mismo `sub` no hace nada (idempotente),
        pero uno distinto es un `ConditionFailedError` en vez de mover el alias. Un `sub`
        que ya es de otro usuario es un `AlreadyExistsError` y no cambia nada.
        """
        current = self.get(user_id)
        if current is None:
            raise ConditionFailedError(f"User {user_id} does not exist")
        if current.cognito_sub == sub:
            return current
        if current.cognito_sub is not None:
            raise ConditionFailedError(f"User {user_id} is already linked to another Cognito sub")

        try:
            s.run_transaction(
                self.db,
                [
                    s.tx_update(
                        keys.key(keys.user_pk(user_id)),
                        set_={"cognito_sub": sub},
                        condition="attribute_exists(#pk) AND attribute_not_exists(#sub)",
                        names={"#pk": keys.PK, "#sub": "cognito_sub"},
                    ),
                    s.tx_put(_items.user_sub_alias_item(sub, user_id), condition=_NEW),
                ],
                exists_error=f"Cognito sub {sub} is already linked to another user",
                failed_error=f"User {user_id} changed while it was being linked",
            )
        except ConditionFailedError:
            # Otra corrida vinculó este mismo `sub` en el medio: para el que llama es un éxito.
            again = self.get(user_id)
            if again is not None and again.cognito_sub == sub:
                return again
            raise
        return dataclasses.replace(current, cognito_sub=sub)

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
                s.tx_put(_items.user_alias_item(updated.email, user_id), condition=_NEW),
            ]
        s.run_transaction(
            self.db,
            ops,
            exists_error=f"User with email {updated.email} already exists",
            failed_error=f"User {user_id} changed while it was being updated",
        )
        return updated

    def delete(self, user: User) -> None:
        """Baja del usuario **y** de sus alias, para que el email se pueda reusar y el
        `sub` deje de resolver a nadie.

        El borrado del usuario se condiciona a que su `cognito_sub` sea el de `user`: si
        lo vincularon después de leerlo, borrar sin su alias lo dejaría huérfano.
        """
        user_key = keys.key(keys.user_pk(user.id))
        if user.cognito_sub is None:
            ops = [s.tx_delete(user_key, condition="attribute_not_exists(cognito_sub)")]
        else:
            ops = [
                s.tx_delete(
                    user_key,
                    # `attribute_not_exists(PK)`: borrar uno que ya no está sigue sin fallar.
                    condition="attribute_not_exists(PK) OR cognito_sub = :sub",
                    values={":sub": user.cognito_sub},
                ),
                s.tx_delete(keys.key(keys.user_sub(user.cognito_sub)[keys.PK])),
            ]
        ops.append(s.tx_delete(keys.key(keys.user_email(user.email)[keys.PK])))
        s.run_transaction(
            self.db,
            ops,
            failed_error=f"User {user.id} changed while it was being deleted",
        )
