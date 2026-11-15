"""El job de vencimientos (§3.4).

    handler: app.notifications.deadline_scanner.handler

En AWS lo dispara una rule de EventBridge (`rate(15 minutes)`); en local,
`app.notifications.local` lo corre cada `NOTIFICATIONS_SCAN_SECONDS`. **No notifica ni vence
nada**: marca en la reserva que el plazo venció, y el aviso sale por el stream como cualquier
otro cambio. Vencer (liberar el ejemplar) sigue siendo `POST /reservations/expire`.
"""

from __future__ import annotations

import logging
from typing import Any

from ..persistence.dynamo import get_dynamo
from ..services import notification_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, int]:
    marked = notification_service.scan_deadlines(get_dynamo())
    if marked:
        logger.info("deadline_scanner: marked %d reservations", marked)
    return {"marked": marked}
