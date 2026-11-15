"""El notificador: del stream de la tabla al bus (§3 y §4).

    handler: app.notifications.notifier.handler

En AWS es una Lambda con un *event source mapping* al stream (filtrado a `RES#…` y a los
`REMOVE` por TTL de `INBOX#…`); en local, `app.notifications.local` le pasa los mismos
registros desde DynamoDB Local. Por cada registro:

- `detect()` dice qué eventos de reserva representa, y cada uno se publica en el bus.
- Si es el borrado por TTL de una notificación **no leída**, descuenta 1 del contador de esa
  bandeja (es el único borrado que no pasa por `NotificationRepository`).

**Un error hace fallar el lote** y Lambda lo reintenta (con `bisect_batch_on_function_error`
en el mapping, un registro venenoso termina aislado en vez de congelar el shard). Republicar es
inocuo: la bandeja es idempotente. Descontar no lo es, pero el contador se defiende de la
deriva (se lee recortado a ≥ 0 y «leer todas» lo recalcula, §5.3).
"""

from __future__ import annotations

import logging
from typing import Any

from ..persistence.dynamo import Dynamo, get_dynamo
from ..persistence.repositories import NotificationRepository
from . import events
from .bus import Bus, get_bus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def process(db: Dynamo, records: list[dict[str, Any]], *, bus: Bus) -> dict[str, int]:
    published = decremented = 0
    for record in records:
        inbox = events.expired_unread_inbox(record)
        if inbox is not None:
            NotificationRepository(db).decrement_unread(*inbox)
            decremented += 1
            continue
        for event in events.detect(record):
            bus.publish(event)
            published += 1
            logger.info("notifier: published %s", event.event_id)
    return {"published": published, "decremented": decremented}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, int]:
    db = get_dynamo()
    return process(db, event.get("Records", []), bus=get_bus(db))
