"""Bandejas de notificaciones sobre DynamoDB (`notifications-roadmap.md` §5.2 y §5.3).

Una partición por bandeja (`INBOX#USER#<id>` o `INBOX#LIB#<id>`) con un ítem por notificación
(`NOTIF#<occurred_at>#<event_id>`) y el contador de no leídas (`UNREAD`). **Todo lo que escribe
o borra una notificación pasa por acá y mueve el contador en la misma transacción**: un camino
que se lo saltee lo desalinea para siempre.

- **Entregar** es idempotente: el `Put` va con `attribute_not_exists(PK)` y la SK sale del
  evento, así que un evento repetido choca contra su propio ítem y no suma nada.
- **El id público y el cursor son la SK en base64url**: marcar como leída es un `UpdateItem`
  directo, sin buscar. Al decodificarlos se rearma la clave con la bandeja *del que pregunta*,
  así que un id o un cursor de otra bandeja no lee nada ajeno.
- **Defensas contra la deriva del contador**: se lee recortado a ≥ 0, y «leer todas» lo deja en
  0 si al terminar no queda ninguna sin leer.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any

from ..dynamo import Dynamo
from ..entities import InboxKind, Notification
from ..errors import AlreadyExistsError, ConditionFailedError, InvalidReferenceError
from ..table import TTL_ATTRIBUTE
from .. import keys
from . import _items
from . import _support as s

_KIND_BACK = {v: k for k, v in _items.INBOX_KIND_KEYS.items()}
_NEW = "attribute_not_exists(PK)"
_UNREAD_NOTIFICATION = "attribute_exists(PK) AND attribute_not_exists(read_at)"
# Una transacción de «leer todas»: hasta 99 notificaciones y el contador.
_READ_ALL_CHUNK = s.TRANSACTION_LIMIT - 1

Inbox = tuple[InboxKind, int]


def _encode(sk: str) -> str:
    return base64.urlsafe_b64encode(sk.encode()).rstrip(b"=").decode()


def _decode(token: str) -> str:
    """La SK de un id o un cursor. `InvalidReferenceError` si no es uno."""
    try:
        sk = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidReferenceError("Malformed notification reference") from exc
    if not keys.is_notification_sk(sk):
        raise InvalidReferenceError("Malformed notification reference")
    return sk


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())


class NotificationRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    # -- formato --------------------------------------------------------------

    @staticmethod
    def _pk(kind: InboxKind, owner_id: int) -> str:
        return _items.inbox_pk(kind, owner_id)

    @staticmethod
    def parse_inbox(pk: str) -> Inbox | None:
        """La bandeja de una PK, o `None` si no es de una bandeja. Para quien lee el stream."""
        parsed = keys.parse_inbox_pk(pk)
        return (_KIND_BACK[parsed[0]], parsed[1]) if parsed else None

    @staticmethod
    def _entity(item: dict[str, Any]) -> Notification:
        return s.from_item(Notification, item, id=_encode(item[keys.SK]))

    # -- lecturas -------------------------------------------------------------

    def get(self, kind: InboxKind, owner_id: int, notification_id: str) -> Notification | None:
        item = s.get_item(self.db, self._pk(kind, owner_id), _decode(notification_id))
        return self._entity(item) if item else None

    def list(
        self,
        kind: InboxKind,
        owner_id: int,
        *,
        now: datetime,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[Notification], str | None]:
        """Una página de la bandeja, de la más nueva a la más vieja, y el cursor de la
        siguiente (`None` si no hay más).

        Filtra las vencidas (`ttl_epoch <= now`): DynamoDB las borra con hasta ~48 h de atraso.
        Como `Limit` cuenta antes del filtro, pide de a lo que falta hasta llenar la página.
        """
        pk = self._pk(kind, owner_id)
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
            "FilterExpression": "#ttl > :now",
            "ExpressionAttributeNames": {"#ttl": TTL_ATTRIBUTE},
            "ExpressionAttributeValues": {
                ":pk": pk,
                ":prefix": keys.NOTIFICATION_PREFIX,
                ":now": _epoch(now),
            },
            "ScanIndexForward": False,
            "ConsistentRead": True,
        }
        if cursor is not None:
            kwargs["ExclusiveStartKey"] = {keys.PK: pk, keys.SK: _decode(cursor)}

        found: list[Notification] = []
        last: dict[str, Any] | None = None
        while len(found) < limit:
            page = self.db.table.query(Limit=limit - len(found), **kwargs)
            found.extend(self._entity(i) for i in page["Items"])
            last = page.get("LastEvaluatedKey")
            if last is None:
                break
            kwargs["ExclusiveStartKey"] = last
        return found, (_encode(last[keys.SK]) if last else None)

    def unread_count(self, kind: InboxKind, owner_id: int) -> int:
        item = s.get_item(self.db, self._pk(kind, owner_id), keys.UNREAD)
        return max(int(item.get("unread", 0)), 0) if item else 0

    # -- escrituras -----------------------------------------------------------

    def deliver(
        self,
        notifications: list[tuple[InboxKind, int, Notification]],
        event_id: str,
        *,
        require_user: int | None = None,
    ) -> bool:
        """Escribe las notificaciones de un evento y suma 1 al contador de cada bandeja, todo
        en **una** transacción: llegan todas o ninguna. Devuelve `False` si el evento ya se
        había entregado (no escribe nada).

        `require_user`: el usuario dueño de una de las bandejas tiene que seguir existiendo
        (un `ConditionCheck` en la misma transacción). Si se borró entre medio, levanta
        `ConditionFailedError` y quien llama decide entregar solo a la sede.
        """
        ops: list[dict[str, Any]] = []
        for kind, owner_id, notification in notifications:
            pk = self._pk(kind, owner_id)
            sk = keys.notification_sk(notification.created_at, event_id)
            ops.append(s.tx_put(_items.notification_item(pk, sk, notification), condition=_NEW))
            ops.append(self._add_unread(pk, 1))
        if require_user is not None:
            ops.append(s.tx_check(keys.key(keys.user_pk(require_user)), "attribute_exists(PK)"))
        try:
            s.run_transaction(
                self.db,
                ops,
                exists_error=f"Event {event_id} was already delivered",
                failed_error=f"User {require_user} no longer exists",
            )
        except AlreadyExistsError:
            return False
        return True

    def mark_read(
        self, kind: InboxKind, owner_id: int, notification_id: str, *, by: int, at: datetime
    ) -> Notification | None:
        """Marca una como leída y descuenta 1, juntos. Idempotente: si ya estaba leída no
        descuenta de nuevo y la devuelve como está. `None` si no existe en esa bandeja."""
        pk, sk = self._pk(kind, owner_id), _decode(notification_id)
        try:
            s.run_transaction(self.db, [self._read_op(pk, sk, by, at), self._add_unread(pk, -1)])
        except ConditionFailedError:
            pass  # ya leída, o no existe: lo dice la lectura de abajo
        item = s.get_item(self.db, pk, sk)
        return self._entity(item) if item else None

    def mark_all_read(self, kind: InboxKind, owner_id: int, *, by: int, at: datetime) -> int:
        """Marca como leídas todas las no leídas y devuelve cuántas marcó.

        De a 99 notificaciones más el contador por transacción. Si una se marcó en el medio
        (otro librarian de la sede), ese lote se rehace de a una. Al final, si no queda ninguna
        sin leer, deja el contador en 0: corrige cualquier deriva acumulada.
        """
        pk = self._pk(kind, owner_id)
        unread = self._unread_keys(pk)
        marked = 0
        for start in range(0, len(unread), _READ_ALL_CHUNK):
            chunk = unread[start : start + _READ_ALL_CHUNK]
            ops = [self._read_op(pk, sk, by, at) for sk in chunk]
            try:
                s.run_transaction(self.db, [*ops, self._add_unread(pk, -len(chunk))])
                marked += len(chunk)
            except ConditionFailedError:
                for op in ops:
                    try:
                        s.run_transaction(self.db, [op, self._add_unread(pk, -1)])
                        marked += 1
                    except ConditionFailedError:
                        pass
        self._reset_counter_if_all_read(pk)
        return marked

    def decrement_unread(self, kind: InboxKind, owner_id: int) -> None:
        """Descuenta 1. Solo para cuando DynamoDB borró por TTL una notificación no leída: es
        el único borrado que no pasa por este repository (lo ve el notificador en el stream)."""
        s.run_transaction(self.db, [self._add_unread(self._pk(kind, owner_id), -1)])

    # -- internos -------------------------------------------------------------

    @staticmethod
    def _add_unread(pk: str, delta: int) -> dict[str, Any]:
        return {
            "Update": {
                "Key": keys.key(pk, keys.UNREAD),
                "UpdateExpression": "ADD unread :delta",
                "ExpressionAttributeValues": {":delta": delta},
            }
        }

    @staticmethod
    def _read_op(pk: str, sk: str, by: int, at: datetime) -> dict[str, Any]:
        return s.tx_update(
            keys.key(pk, sk), set_={"read_at": at, "read_by": by}, condition=_UNREAD_NOTIFICATION
        )

    def _unread_keys(self, pk: str) -> list[str]:
        items = s.query_all(
            self.db,
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            FilterExpression="attribute_not_exists(read_at)",
            ProjectionExpression="SK",
            ExpressionAttributeValues={":pk": pk, ":prefix": keys.NOTIFICATION_PREFIX},
            ConsistentRead=True,
        )
        return [i[keys.SK] for i in items]

    def _reset_counter_if_all_read(self, pk: str) -> None:
        """Pone el contador en 0 si no queda ninguna sin leer. Condicionado al valor que se
        leyó antes de mirar: si una entrega lo movió en el medio, no lo pisa."""
        counter = s.get_item(self.db, pk, keys.UNREAD)
        if counter is None or self._unread_keys(pk):
            return
        try:
            s.run_transaction(
                self.db,
                [
                    s.tx_update(
                        keys.key(pk, keys.UNREAD),
                        set_={"unread": 0},
                        condition="unread = :seen",
                        values={":seen": counter["unread"]},
                    )
                ],
            )
        except ConditionFailedError:
            pass
