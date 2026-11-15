"""Detección: de un registro del stream de DynamoDB a los eventos de reserva que representa.

**Puro, sin I/O.** `detect(record)` mira la imagen vieja y la nueva de un ítem `RES#<id>`/`META`
y devuelve 0 o más `ReservationEvent`. Se testea con registros reales del stream, sin AWS, y es
lo único que decide qué cuenta como «algo que pasó» (`notifications-roadmap.md` §4):

| `eventName` | Condición (Old → New)                                                  | Evento           |
|-------------|------------------------------------------------------------------------|------------------|
| `INSERT`    | `origin` ≠ `seed`                                                      | `created`        |
| `MODIFY`    | `picked_up`: `false → true`                                            | `picked_up`      |
| `MODIFY`    | aparece `cancelled_at`, `close_reason ∈ {cancelled, lost}`             | `cancelled`      |
| `MODIFY`    | aparece `cancelled_at`, `close_reason = expired`, Old sin marca previa | `pickup_expired` |
| `MODIFY`    | aparece `pickup_deadline_notified_at`                                  | `pickup_expired` |
| `MODIFY`    | aparece `return_deadline_notified_at`                                  | `return_overdue` |
| `MODIFY`    | aparece `returned_at`, `close_reason = returned`                       | `returned`       |
| `MODIFY`    | aparece `returned_at`, `close_reason = lost`                           | — (interno)      |
| `REMOVE`    | — (las reservas no se borran)                                          | —                |

Una reserva cerrada sin `close_reason` (la escribió código anterior a la fase 1) se toma como
cancelada o devuelta según la columna: es lo que significaba antes.

**El `event_id` es determinista**: sale de la reserva, el tipo y `occurred_at`, que salen de la
imagen y no del reloj. Si el stream reentrega un registro, el evento es el mismo, y la bandeja
lo descarta (§5.2). En los vencimientos `occurred_at` es el `expires_at`, así una extensión
seguida de un nuevo vencimiento es otro evento.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.types import TypeDeserializer

from ..persistence import keys
from ..persistence.entities import SEED_ORIGIN, CancelledBy, CloseReason, Reservation
from ..persistence.repositories import _support as s

_deserializer = TypeDeserializer()


class EventType(str, enum.Enum):
    created = "reservation.created"
    picked_up = "reservation.picked_up"
    cancelled = "reservation.cancelled"
    pickup_expired = "reservation.pickup_expired"
    return_overdue = "reservation.return_overdue"
    returned = "reservation.returned"

    @property
    def short(self) -> str:
        return self.value.removeprefix("reservation.")


class Actor(str, enum.Enum):
    """Quién provocó el evento: el lector, la sede o el sistema (los vencimientos)."""

    user = "user"
    library = "library"
    system = "system"


@dataclass(frozen=True, kw_only=True)
class ReservationEvent:
    type: EventType
    occurred_at: datetime
    actor: Actor
    # La reserva como quedó después del cambio (la imagen nueva).
    reservation: Reservation

    @property
    def event_id(self) -> str:
        """`r123.pickup_expired.20261120T235959Z`. A segundos, como el ejemplo del contrato: dos
        eventos del mismo tipo de una misma reserva nunca caen en el mismo segundo (el único
        repetible, el vencimiento, depende de `expires_at`, que una extensión mueve)."""
        stamp = self.occurred_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"r{self.reservation.id}.{self.type.short}.{stamp}"

    def to_message(self) -> dict[str, Any]:
        """El mensaje que se publica en SNS: el contrato con cualquier suscriptor (§4). Lleva
        ids, no nombres ni emails; los textos los arma quien entrega."""
        r = self.reservation
        return {
            "event_id": self.event_id,
            "type": self.type.value,
            "occurred_at": _iso_seconds(self.occurred_at),
            "actor": self.actor.value,
            "reservation": {
                "id": r.id,
                "user_id": r.user_id,
                "library_id": r.library_id,
                "physical_book_id": r.physical_book_id,
                "isbn": r.isbn,
                "expires_at": _iso_seconds(r.expires_at),
            },
        }


def _iso_seconds(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _image(record: dict[str, Any], name: str) -> dict[str, Any] | None:
    raw = record.get("dynamodb", {}).get(name)
    return _deserializer.deserialize({"M": raw}) if raw else None


def is_reservation_record(record: dict[str, Any]) -> bool:
    """¿Es un cambio del ítem principal de una reserva? Lo mismo que filtra el event source
    mapping en AWS; acá se repite porque en local el poller no filtra."""
    key = _image(record, "Keys") or {}
    return keys.is_reservation_pk(str(key.get(keys.PK, ""))) and key.get(keys.SK) == keys.META


def _record_time(record: dict[str, Any]) -> datetime:
    """`ApproximateCreationDateTime` del registro: fijo para ese registro, así que sigue
    siendo determinista ante una reentrega. Solo es el respaldo de un dato que falta."""
    raw = record.get("dynamodb", {}).get("ApproximateCreationDateTime")
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc)
    if raw is not None:
        return datetime.fromtimestamp(float(raw), timezone.utc)
    raise ValueError("Stream record without ApproximateCreationDateTime")


def _appeared(old: Reservation, new: Reservation, field: str) -> bool:
    return getattr(old, field) is None and getattr(new, field) is not None


def detect(record: dict[str, Any]) -> list[ReservationEvent]:
    """Los eventos de reserva de un registro del stream. Ver la tabla del módulo."""
    if not is_reservation_record(record):
        return []
    name = record.get("eventName")
    new_image = _image(record, "NewImage")
    if name == "REMOVE" or new_image is None:
        return []
    new = s.from_item(Reservation, new_image)

    def event(type_: EventType, occurred_at: datetime, actor: Actor) -> ReservationEvent:
        return ReservationEvent(type=type_, occurred_at=occurred_at, actor=actor, reservation=new)

    if name == "INSERT":
        if new.origin == SEED_ORIGIN:
            return []  # historia sembrada, no algo que acaba de pasar
        return [event(EventType.created, new.reserved_at or _record_time(record), Actor.user)]

    old_image = _image(record, "OldImage")
    if name != "MODIFY" or old_image is None:
        return []
    old = s.from_item(Reservation, old_image)
    events: list[ReservationEvent] = []

    if not old.picked_up and new.picked_up:
        events.append(event(EventType.picked_up, new.picked_up_at or _record_time(record), Actor.library))

    if _appeared(old, new, "cancelled_at"):
        reason = new.close_reason or CloseReason.cancelled
        if reason is CloseReason.expired:
            # Si el job ya avisó el vencimiento (la marca está en Old), vencer no lo repite.
            if old.pickup_deadline_notified_at is None:
                events.append(event(EventType.pickup_expired, new.expires_at, Actor.system))
        elif reason in (CloseReason.cancelled, CloseReason.lost):
            actor = Actor.user if new.cancelled_by is CancelledBy.user else Actor.library
            events.append(event(EventType.cancelled, new.cancelled_at, actor))

    if _appeared(old, new, "pickup_deadline_notified_at"):
        events.append(event(EventType.pickup_expired, new.expires_at, Actor.system))

    if _appeared(old, new, "return_deadline_notified_at"):
        events.append(event(EventType.return_overdue, new.expires_at, Actor.system))

    if _appeared(old, new, "returned_at"):
        reason = new.close_reason or CloseReason.returned
        if reason is CloseReason.returned:
            events.append(event(EventType.returned, new.returned_at, Actor.library))
        # `lost` con el libro prestado: es interno de la sede, el lector no tiene nada que hacer.

    return events
