"""El inbox-writer: de un mensaje de SNS a las dos notificaciones (§3 y §5).

    handler: app.notifications.inbox_writer.handler

Suscripto al topic con `protocol = "lambda"`: SNS lo invoca de forma **asíncrona**, con
`Records[].Sns.Message` (en la práctica, un registro por invocación). Si algo falla, la
excepción sube y Lambda reintenta la invocación 2 veces; si las tres fallan, el aviso se pierde
y queda en CloudWatch (§3.3). La reserva nunca se pierde: vive en la base.

Los reintentos y los duplicados de SNS (entrega *al menos una vez*) no duplican nada: el id de
cada notificación sale del evento y la bandeja descarta lo que ya tiene (§5.2).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..persistence.dynamo import Dynamo, get_dynamo
from ..services import notification_service
from .events import ReservationEvent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def process(db: Dynamo, event: dict[str, Any]) -> dict[str, int]:
    delivered = duplicates = 0
    for record in event.get("Records", []):
        message = json.loads(record["Sns"]["Message"])
        reservation_event = ReservationEvent.from_message(message)
        if notification_service.deliver(db, reservation_event):
            delivered += 1
        else:
            duplicates += 1
        # Solo ids: los logs van a CloudWatch (como `cognito_triggers.py`).
        logger.info("inbox_writer: %s", reservation_event.event_id)
    return {"delivered": delivered, "duplicates": duplicates}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, int]:
    return process(get_dynamo(), event)
