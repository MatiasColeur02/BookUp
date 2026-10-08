"""Creación de la tabla `bookup` y sus cuatro GSIs.

`ensure_table()` es idempotente y espera a que la tabla y sus índices estén `ACTIVE`.
Lo corre el servicio `dynamodb-init` del compose y, más adelante, el seed y la suite de
tests. En AWS la tabla la crea la infraestructura como código, no la app; esto es para
local y para tests.

**No versiona.** No hay migraciones ni nada que lleve la forma de la tabla de versión en
versión. Si la tabla ya existe con otros índices, `ensure_table()` no intenta repararla: falla con un mensaje que lo dice, porque cambiar un GSI sobre una tabla con
datos es un backfill escrito a mano (ver `ROADMAP.md` §9).

    python -m app.persistence.table
"""

from __future__ import annotations

import logging
import time
from typing import Any

from botocore.exceptions import ClientError

from ..config import settings
from . import keys
from .dynamo import Dynamo, connect

logger = logging.getLogger(__name__)

# (nombre del índice, atributo de PK, atributo de SK). Qué guarda cada uno está en
# `keys.py` y en `ROADMAP.md` §3.2.
INDEXES: tuple[tuple[str, str, str], ...] = (
    (keys.GSI1, keys.GSI1_PK, keys.GSI1_SK),  # listados ordenados
    (keys.GSI2, keys.GSI2_PK, keys.GSI2_SK),  # hijos de X
    (keys.GSI3, keys.GSI3_PK, keys.GSI3_SK),  # por sede
    (keys.GSI4, keys.GSI4_PK, keys.GSI4_SK),  # reservas abiertas (disperso)
)

WAIT_TIMEOUT_SECONDS = 120
WAIT_POLL_SECONDS = 0.5


class TableSchemaError(RuntimeError):
    """La tabla existe pero no tiene la forma que espera el código."""


def table_definition(table_name: str) -> dict[str, Any]:
    """Los argumentos de `create_table` para la tabla única."""
    attribute_names = [keys.PK, keys.SK]
    for _, pk_attr, sk_attr in INDEXES:
        attribute_names += [pk_attr, sk_attr]

    return {
        "TableName": table_name,
        "AttributeDefinitions": [
            {"AttributeName": name, "AttributeType": "S"} for name in attribute_names
        ],
        "KeySchema": [
            {"AttributeName": keys.PK, "KeyType": "HASH"},
            {"AttributeName": keys.SK, "KeyType": "RANGE"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": name,
                "KeySchema": [
                    {"AttributeName": pk_attr, "KeyType": "HASH"},
                    {"AttributeName": sk_attr, "KeyType": "RANGE"},
                ],
                # ALL: el objetivo es que una lectura sea un solo Query, sin ir a la tabla
                # base a buscar el resto del ítem. Cuesta almacenamiento, no latencia.
                "Projection": {"ProjectionType": "ALL"},
            }
            for name, pk_attr, sk_attr in INDEXES
        ],
        # On-Demand: el tráfico de una red de bibliotecas es irregular y evita
        # dimensionar a ojo (ROADMAP §7.6).
        "BillingMode": "PAY_PER_REQUEST",
        # El stream alimenta al indexador de OpenSearch (fase 6). Prenderlo después sobre
        # una tabla con datos pierde los eventos anteriores, así que se crea ya prendido.
        "StreamSpecification": {"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
    }


def _describe(dynamo: Dynamo) -> dict[str, Any] | None:
    try:
        return dynamo.client.describe_table(TableName=dynamo.table_name)["Table"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise


def _index_shape(description: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    return {
        gsi["IndexName"]: tuple(part["AttributeName"] for part in gsi["KeySchema"])
        for gsi in description.get("GlobalSecondaryIndexes", [])
    }


def _check_schema(dynamo: Dynamo, description: dict[str, Any]) -> None:
    """Falla si la tabla existente no coincide con `INDEXES` y con la clave primaria."""
    primary = tuple(part["AttributeName"] for part in description["KeySchema"])
    if primary != (keys.PK, keys.SK):
        raise TableSchemaError(
            f"Table {dynamo.table_name!r} has key schema {primary}, expected "
            f"{(keys.PK, keys.SK)}"
        )

    expected = {name: (pk_attr, sk_attr) for name, pk_attr, sk_attr in INDEXES}
    actual = _index_shape(description)
    if actual != expected:
        raise TableSchemaError(
            f"Table {dynamo.table_name!r} has indexes {actual}, expected {expected}. "
            "There are no migrations: drop the table (local) or backfill by hand."
        )


def _wait_until_active(dynamo: Dynamo) -> dict[str, Any]:
    """Espera a que la tabla **y cada GSI** estén `ACTIVE`, y devuelve su descripción.

    El waiter `table_exists` de boto3 solo mira la tabla; un GSI recién creado puede
    seguir en `CREATING` y un `Query` contra él falla con `ValidationException`.
    """
    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
    while True:
        description = _describe(dynamo)
        if description is not None:
            gsi_statuses = [
                gsi["IndexStatus"] for gsi in description.get("GlobalSecondaryIndexes", [])
            ]
            if description["TableStatus"] == "ACTIVE" and all(s == "ACTIVE" for s in gsi_statuses):
                return description
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Table {dynamo.table_name!r} was not ACTIVE after {WAIT_TIMEOUT_SECONDS}s"
            )
        time.sleep(WAIT_POLL_SECONDS)


def ensure_table(dynamo: Dynamo) -> bool:
    """Crea la tabla y los GSIs si faltan. Devuelve `True` si los creó.

    Idempotente: sobre una tabla que ya existe con la forma correcta no hace nada, y
    si existe con otra forma levanta `TableSchemaError`.
    """
    description = _describe(dynamo)
    created = description is None
    if created:
        try:
            dynamo.client.create_table(**table_definition(dynamo.table_name))
            logger.info("Created table %s", dynamo.table_name)
        except ClientError as exc:
            # Otro proceso la creó entre el describe y el create (p. ej. el seed y
            # dynamodb-init arrancando juntos): da igual quién ganó.
            if exc.response["Error"]["Code"] != "ResourceInUseException":
                raise
            created = False

    description = _wait_until_active(dynamo)
    _check_schema(dynamo, description)
    return created


def drop_table(dynamo: Dynamo) -> None:
    """Borra la tabla si existe y espera a que desaparezca. Pensado para tests."""
    try:
        dynamo.client.delete_table(TableName=dynamo.table_name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return
        raise
    dynamo.client.get_waiter("table_not_exists").wait(TableName=dynamo.table_name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not settings.dynamo_table:
        raise SystemExit("DYNAMO_TABLE is not set")
    dynamo = connect(
        settings.dynamo_table,
        endpoint_url=settings.dynamo_endpoint_url,
        region=settings.aws_region,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
    )
    created = ensure_table(dynamo)
    names = ", ".join(name for name, _, _ in INDEXES)
    print(
        f"Table {dynamo.table_name!r} {'created' if created else 'already exists'} "
        f"(ACTIVE, indexes: {names})"
    )


if __name__ == "__main__":
    main()
