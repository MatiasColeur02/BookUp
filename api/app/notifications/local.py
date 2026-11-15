"""Las notificaciones en local: lo que en AWS son dos Lambdas disparadas por AWS (§9.2).

    python -m app.notifications.local      # servicio `notifier` del compose

Dos hilos, con los mismos handlers que en AWS:

1. **El notificador**: sigue el stream de DynamoDB Local (`app/streams.py`, el mismo poller que
   el indexador) y le pasa los registros a `notifier.process`. Con `NOTIFICATIONS_BUS=inline`
   el bus termina en `inbox_writer.process`, con el formato de SNS → Lambda.
2. **El job de vencimientos**: `deadline_scanner.handler` cada `NOTIFICATIONS_SCAN_SECONDS`
   (en AWS, una rule de EventBridge).

A diferencia del indexador, no hay con qué reconstruir lo perdido: lo que se escriba con este
servicio parado no notifica (se engancha al final del stream). Los vencimientos sí se recuperan,
porque el job mira el estado y no el stream.
"""

from __future__ import annotations

import logging
import threading
import time

from ..config import settings
from ..persistence.dynamo import get_dynamo
from ..streams import follow
from . import deadline_scanner, notifier
from .bus import get_bus

logger = logging.getLogger(__name__)


def follow_stream(attached: threading.Event) -> None:
    db = get_dynamo()  # uno por hilo: el recurso de boto3 no es thread-safe
    bus = get_bus(db)

    def on_records(records: list[dict]) -> None:
        result = notifier.process(db, records, bus=bus)
        if any(result.values()):
            logger.info("notifier: %s", result)

    follow(db, on_records, on_attach=attached.set, name="notifier")


def scan_forever(attached: threading.Event, every_seconds: float) -> None:
    # El job escribe marcas que el notificador tiene que ver en el stream: si corriera antes de
    # que el poller se enganche (al final del stream), esas marcas no notificarían nunca.
    attached.wait()
    while True:
        try:
            deadline_scanner.handler()
        except Exception:  # noqa: BLE001 — la tabla puede no estar todavía; se reintenta
            logger.exception("deadline_scanner failed; retrying")
        time.sleep(every_seconds)


def run() -> None:
    if not settings.notifications_bus:
        logger.warning("NOTIFICATIONS_BUS is empty: events are detected but not delivered")
    attached = threading.Event()
    threading.Thread(
        target=scan_forever,
        args=(attached, settings.notifications_scan_seconds),
        daemon=True,
        name="scanner",
    ).start()
    follow_stream(attached)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(threadName)s %(message)s")
    run()
