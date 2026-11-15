"""El bus: cómo viaja un evento detectado desde el notificador hasta el inbox-writer (§9.1).

| `NOTIFICATIONS_BUS` | Publica en                                                     | Se usa en         |
|---------------------|----------------------------------------------------------------|-------------------|
| `sns`               | El topic de `NOTIFICATIONS_TOPIC_ARN`                          | AWS               |
| `inline`            | `inbox_writer.process`, en el mismo proceso                    | compose y `pytest`|
| vacío               | Nada: las notificaciones quedan apagadas                       | como Redis sin URL|

`inline` **no se saltea el formato**: serializa el mismo mensaje que iría a SNS y lo envuelve en
un evento con la forma del que SNS le pasa a Lambda (`Records[].Sns.Message`), así en local
corre el mismo código del inbox-writer que en AWS. Lo único que no se ejercita es el `Publish`.

`message_body` y `message_attributes` son el contrato (§4): los dos buses los usan, así no
pueden divergir.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Protocol

import boto3

from ..config import settings
from ..persistence.dynamo import Dynamo
from .events import ReservationEvent

logger = logging.getLogger(__name__)

# El ARN que lleva el evento inline cuando no hay topic real: es solo un rótulo.
LOCAL_TOPIC_ARN = "arn:aws:sns:us-east-1:000000000000:bookup-reservation-events"


class Bus(Protocol):
    def publish(self, event: ReservationEvent) -> None: ...


def message_body(event: ReservationEvent) -> str:
    return json.dumps(event.to_message(), separators=(",", ":"), ensure_ascii=False)


def message_attributes(event: ReservationEvent) -> dict[str, str]:
    """`event_type` permite filter policies por suscripción (§3.2): un email futuro podría
    suscribirse solo a `return_overdue`."""
    return {"event_type": event.type.value}


# ---------------------------------------------------------------------------
# Buses
# ---------------------------------------------------------------------------


class NullBus:
    """Notificaciones apagadas: detectar sigue funcionando, publicar no hace nada."""

    def publish(self, event: ReservationEvent) -> None:
        logger.debug("notifications disabled; dropping %s", event.event_id)


class SnsBus:
    def __init__(self, topic_arn: str, client: Any):
        self.topic_arn = topic_arn
        self.client = client

    def publish(self, event: ReservationEvent) -> None:
        self.client.publish(
            TopicArn=self.topic_arn,
            Message=message_body(event),
            MessageAttributes={
                name: {"DataType": "String", "StringValue": value}
                for name, value in message_attributes(event).items()
            },
        )


class InlineBus:
    """Entrega en el mismo proceso, pasando por el formato de SNS → Lambda."""

    def __init__(self, db: Dynamo, topic_arn: str = LOCAL_TOPIC_ARN):
        self.db = db
        self.topic_arn = topic_arn

    def publish(self, event: ReservationEvent) -> None:
        from . import inbox_writer  # inbox_writer → services → events; evita el ciclo al importar

        inbox_writer.process(self.db, sns_lambda_event(event, topic_arn=self.topic_arn))


def sns_lambda_event(event: ReservationEvent, *, topic_arn: str = LOCAL_TOPIC_ARN) -> dict[str, Any]:
    """El evento con el que SNS invoca a una Lambda suscripta al topic (un registro por
    invocación). Sin firma: nadie la verifica en una suscripción `lambda`."""
    subscription = f"{topic_arn}:{uuid.uuid4()}"
    return {
        "Records": [
            {
                "EventSource": "aws:sns",
                "EventVersion": "1.0",
                "EventSubscriptionArn": subscription,
                "Sns": {
                    "Type": "Notification",
                    "MessageId": str(uuid.uuid4()),
                    "TopicArn": topic_arn,
                    "Subject": None,
                    "Message": message_body(event),
                    "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                    "SignatureVersion": "1",
                    "Signature": "",
                    "SigningCertUrl": "",
                    "UnsubscribeUrl": "",
                    # Del lado de Lambda los atributos llegan como `Type`/`Value`, no como
                    # `DataType`/`StringValue` del `Publish`.
                    "MessageAttributes": {
                        name: {"Type": "String", "Value": value}
                        for name, value in message_attributes(event).items()
                    },
                },
            }
        ]
    }


@lru_cache(maxsize=None)
def _sns_client(region: str):
    """Cacheado: en Lambda el contenedor se reutiliza entre invocaciones. Las credenciales
    salen de la cadena default de boto3 (el rol de la función)."""
    return boto3.client("sns", region_name=region)


def get_bus(db: Dynamo) -> Bus:
    """El bus según `NOTIFICATIONS_BUS`. `db` solo lo usa el inline, que entrega acá mismo."""
    if settings.notifications_bus == "sns":
        return SnsBus(settings.notifications_topic_arn, _sns_client(settings.aws_region))
    if settings.notifications_bus == "inline":
        return InlineBus(db)
    return NullBus()
