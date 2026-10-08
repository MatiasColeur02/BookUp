"""Reservas sobre DynamoDB: el único repository con transacciones entre dos entidades.

Cada transición (`create`, `mark_picked_up`, `cancel`, `mark_returned`, `expire`, y el cierre
por ejemplar perdido) escribe **la reserva y su ejemplar juntos** con `TransactWriteItems`,
y lo hace *condicionando* en vez de leer y después escribir: el `ConditionExpression` es el
candado (ROADMAP §4.2). Un request que llega segundo no encuentra la condición cumplida y
recibe `ConditionFailedError`, el 409 del contrato.

Los services siguen leyendo antes para dar un mensaje preciso; esas lecturas son
informativas. Lo que garantiza la consistencia es la condición.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

from ..dynamo import Dynamo
from ..entities import PhysicalBookStatus, Reservation
from ..errors import ConditionFailedError
from .. import keys
from . import _items, _support as s

_NEW = "attribute_not_exists(PK)"
_OPEN = "attribute_not_exists(cancelled_at) AND attribute_not_exists(returned_at)"
_STATUS = {"#st": "status"}
# Una reserva cerrada ocupa 2 ítems (la reserva y su ejemplar) en la transacción.
_EXPIRE_CHUNK = s.TRANSACTION_LIMIT // 2


def _status_keys(item: dict[str, Any], status: PhysicalBookStatus) -> dict[str, str]:
    """`GSI2SK`/`GSI3SK` del ejemplar de una reserva en su nuevo estado. La reserva lleva
    `isbn` y `library_id` copiados, así que no hace falta leer el ejemplar para armarlos."""
    copy = keys.copy(
        int(item["physical_book_id"]), item["isbn"], int(item["library_id"]), status.value
    )
    return {keys.GSI2_SK: copy[keys.GSI2_SK], keys.GSI3_SK: copy[keys.GSI3_SK]}


class ReservationRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    @staticmethod
    def _entity(item: dict) -> Reservation:
        return s.from_item(Reservation, item)

    # -- lecturas ----------------------------------------------------------

    def get(self, reservation_id: int) -> Reservation | None:
        item = s.get_item(self.db, keys.reservation_pk(reservation_id))
        return self._entity(item) if item else None

    def list_all(
        self,
        library_id: int | None = None,
        user_id: int | None = None,
        is_open: bool | None = None,
    ) -> list[Reservation]:
        """Reservas, por id. Índice según el filtro: usuario (GSI2), sede (GSI3), las
        abiertas sin más filtro (GSI4, disperso: solo ellas), o la lista completa (GSI1)."""
        names: dict[str, str] = {}
        values: dict[str, Any] = {}
        filters: list[str] = []

        if user_id is not None:
            index = keys.GSI2
            condition = "GSI2PK = :pk AND begins_with(GSI2SK, :prefix)"
            values[":pk"] = keys.user_pk(user_id)
            values[":prefix"] = keys.user_reservations_prefix()
            if library_id is not None:
                filters.append("library_id = :lib")
                values[":lib"] = library_id
        elif library_id is not None:
            index = keys.GSI3
            condition = "GSI3PK = :pk AND begins_with(GSI3SK, :prefix)"
            values[":pk"] = keys.library_pk(library_id)
            values[":prefix"] = keys.library_reservations_prefix()
        elif is_open is True:
            # Sin otro filtro, el índice disperso ya es exactamente "las abiertas".
            index, condition, values[":pk"], is_open = keys.GSI4, "GSI4PK = :pk", keys.OPEN, None
        else:
            index, condition, values[":pk"] = keys.GSI1, "GSI1PK = :pk", keys.LIST_RESERVATIONS

        if is_open is True:
            filters.append(_OPEN)
        elif is_open is False:
            filters.append("(attribute_exists(cancelled_at) OR attribute_exists(returned_at))")

        kwargs: dict[str, Any] = {
            "IndexName": index,
            "KeyConditionExpression": condition,
            "ExpressionAttributeValues": values,
        }
        if names:
            kwargs["ExpressionAttributeNames"] = names
        if filters:
            kwargs["FilterExpression"] = " AND ".join(filters)
        items = s.query_all(self.db, **kwargs)
        return sorted((self._entity(i) for i in items), key=lambda r: r.id)

    def get_open_for_physical_book(self, physical_book_id: int) -> Reservation | None:
        """La reserva abierta de un ejemplar: un puntero (`open_reservation_id`), no un
        índice, porque un ejemplar tiene a lo sumo una."""
        copy = s.get_item(self.db, keys.copy_pk(physical_book_id))
        if copy is None or "open_reservation_id" not in copy:
            return None
        return self.get(int(copy["open_reservation_id"]))

    def list_expired(self, now: datetime) -> list[Reservation]:
        """Abiertas, vencidas y sin retirar. Un Query acotado al índice disperso: recorre
        las decenas de reservas abiertas, no las miles del historial."""
        items = s.query_all(
            self.db,
            IndexName=keys.GSI4,
            KeyConditionExpression="GSI4PK = :open AND GSI4SK < :bound",
            FilterExpression="picked_up = :no",
            ExpressionAttributeValues={
                ":open": keys.OPEN,
                ":bound": keys.expires_before(now),
                ":no": False,
            },
        )
        return sorted((self._entity(i) for i in items), key=lambda r: r.id)

    # -- escrituras --------------------------------------------------------

    def create(self, reservation: Reservation) -> Reservation:
        """Reserva un ejemplar: `available → reserved` y la reserva, en una transacción.

        La condición sobre el ejemplar es el candado. Si dos usuarios reservan a la vez,
        una transacción gana y la otra recibe `ConditionFailedError`.
        """
        copy = s.get_item(self.db, keys.copy_pk(reservation.physical_book_id))
        if copy is None:
            raise ConditionFailedError(
                f"Physical book {reservation.physical_book_id} does not exist"
            )

        reservation_id = s.next_id(self.db, "reservation")
        created = dataclasses.replace(
            reservation,
            id=reservation_id,
            reserved_at=s.now(),
            picked_up=False,
            cancelled_at=None,
            returned_at=None,
            library_id=int(copy["library_id"]),
            isbn=copy["isbn"],
        )
        reservation_item = _items.reservation_item(created)
        s.run_transaction(
            self.db,
            [
                s.tx_update(
                    keys.key(keys.copy_pk(created.physical_book_id)),
                    set_={
                        "status": PhysicalBookStatus.reserved,
                        "open_reservation_id": reservation_id,
                        **_status_keys(reservation_item, PhysicalBookStatus.reserved),
                    },
                    condition="#st = :available",
                    names=_STATUS,
                    values={":available": PhysicalBookStatus.available.value},
                ),
                s.tx_put(reservation_item, condition=_NEW),
                s.tx_put(_items.copy_reservation_item(created.physical_book_id, reservation_id)),
            ],
            failed_error=f"Physical book {created.physical_book_id} is not available",
        )
        return created

    def update_expiry(self, reservation_id: int, expires_at: datetime) -> Reservation:
        """Extiende el vencimiento de una reserva abierta y sin retirar. Mueve también
        `GSI4SK`, que es la clave por la que `list_expired` la encuentra."""
        item = self._require(reservation_id)
        s.run_transaction(
            self.db,
            [
                s.tx_update(
                    keys.key(keys.reservation_pk(reservation_id)),
                    set_={
                        "expires_at": expires_at,
                        **keys.open_reservation_index(reservation_id, expires_at),
                    },
                    condition=f"{_OPEN} AND picked_up = :no",
                    values={":no": False},
                )
            ],
            failed_error=f"Reservation {reservation_id} is no longer open and waiting",
        )
        return dataclasses.replace(self._entity(item), expires_at=expires_at)

    def mark_picked_up(self, reservation_id: int) -> Reservation:
        """Retiro en sede: `reserved → loaned` en el ejemplar y `picked_up` en la reserva."""
        item = self._require(reservation_id)
        s.run_transaction(
            self.db,
            [
                s.tx_update(
                    keys.key(keys.reservation_pk(reservation_id)),
                    set_={"picked_up": True},
                    condition=f"{_OPEN} AND picked_up = :no",
                    values={":no": False},
                ),
                s.tx_update(
                    keys.key(keys.copy_pk(int(item["physical_book_id"]))),
                    set_={
                        "status": PhysicalBookStatus.loaned,
                        **_status_keys(item, PhysicalBookStatus.loaned),
                    },
                    condition="open_reservation_id = :rid AND #st = :reserved",
                    names=_STATUS,
                    values={":rid": reservation_id, ":reserved": "reserved"},
                ),
            ],
            failed_error=f"Reservation {reservation_id} can no longer be picked up",
        )
        return dataclasses.replace(self._entity(item), picked_up=True)

    def cancel(self, reservation_id: int, at: datetime | None = None) -> Reservation:
        """Cancela una reserva abierta que no se retiró y libera el ejemplar."""
        return self._close(reservation_id, at, require_picked_up=False, copy_status="available")

    def mark_returned(self, reservation_id: int, at: datetime | None = None) -> Reservation:
        """Registra la devolución de un ejemplar retirado y lo libera."""
        return self._close(reservation_id, at, require_picked_up=True, copy_status="available")

    def release_lost_copy(self, reservation_id: int, at: datetime | None = None) -> Reservation:
        """Cierra la reserva abierta de un ejemplar que se marca `lost` (prestada → devuelta,
        pendiente → cancelada) y deja el ejemplar en `lost`. Lo llama
        `PhysicalBookRepository.update_status`."""
        return self._close(reservation_id, at, require_picked_up=None, copy_status="lost")

    def expire(self, reservation_ids: list[int], at: datetime | None = None) -> int:
        """Vence las reservas indicadas y libera sus ejemplares. Devuelve cuántas venció.

        Procesa de a 50 (cada una son 2 ítems y el tope es 100). Idempotente: la condición
        "sigue abierta y sin retirar" hace que una reserva ya vencida, cancelada o retirada
        entre medio simplemente no cuente. Si un lote entero se cancela por eso, se rehace
        una a una para no perder las que sí corresponden.
        """
        when = at or s.now()
        expired = 0
        for start in range(0, len(reservation_ids), _EXPIRE_CHUNK):
            chunk = reservation_ids[start : start + _EXPIRE_CHUNK]
            items = s.batch_get(self.db, [keys.key(keys.reservation_pk(i)) for i in chunk])
            ops = [op for item in items for op in self._close_ops(item, when, False, "available")]
            try:
                s.run_transaction(self.db, ops)
                expired += len(items)
            except ConditionFailedError:
                for item in items:
                    try:
                        s.run_transaction(self.db, self._close_ops(item, when, False, "available"))
                        expired += 1
                    except ConditionFailedError:
                        pass
        return expired

    # -- internos ----------------------------------------------------------

    def _require(self, reservation_id: int) -> dict[str, Any]:
        item = s.get_item(self.db, keys.reservation_pk(reservation_id))
        if item is None:
            raise ConditionFailedError(f"Reservation {reservation_id} does not exist")
        return item

    def _close(
        self,
        reservation_id: int,
        at: datetime | None,
        *,
        require_picked_up: bool | None,
        copy_status: str,
    ) -> Reservation:
        item = self._require(reservation_id)
        if require_picked_up is not None and bool(item["picked_up"]) != require_picked_up:
            raise ConditionFailedError(
                f"Reservation {reservation_id} picked_up is {bool(item['picked_up'])}"
            )
        when = at or s.now()
        s.run_transaction(
            self.db,
            self._close_ops(item, when, require_picked_up, copy_status),
            failed_error=f"Reservation {reservation_id} is no longer open",
        )
        column = "returned_at" if item["picked_up"] else "cancelled_at"
        return dataclasses.replace(self._entity(item), **{column: when})

    @staticmethod
    def _close_ops(
        item: dict[str, Any], at: datetime, require_picked_up: bool | None, copy_status: str
    ) -> list[dict[str, Any]]:
        """Las dos operaciones que cierran una reserva.

        - Reserva: setea `returned_at` (si estaba retirada) o `cancelled_at`, y hace
          `REMOVE` de `GSI4PK/GSI4SK`: sale del índice disperso de abiertas.
        - Ejemplar: nuevo estado y `REMOVE open_reservation_id`, condicionado a que siga
          apuntando a *esta* reserva.
        La condición sobre `picked_up` es la exigida (`require_picked_up`) o, si no se
        exige nada, el valor leído: así el cierre refleja el estado real aunque cambie
        entre la lectura y la transacción. Es lo que impide que `expire` venza una
        reserva que se retiró un instante antes.
        """
        reservation_id = int(item["id"])
        picked_up = bool(item["picked_up"]) if require_picked_up is None else require_picked_up
        column = "returned_at" if picked_up else "cancelled_at"
        status = PhysicalBookStatus(copy_status)
        return [
            s.tx_update(
                keys.key(keys.reservation_pk(reservation_id)),
                set_={column: at},
                remove=keys.GSI4_ATTRIBUTES,
                condition=f"{_OPEN} AND picked_up = :picked",
                values={":picked": picked_up},
            ),
            s.tx_update(
                keys.key(keys.copy_pk(int(item["physical_book_id"]))),
                set_={"status": status, **_status_keys(item, status)},
                remove=["open_reservation_id"],
                condition="open_reservation_id = :rid",
                values={":rid": reservation_id},
            ),
        ]
