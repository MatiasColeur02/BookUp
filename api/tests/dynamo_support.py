"""Conexión a DynamoDB Local para los tests que la necesitan.

Nunca se conecta a AWS: sin endpoint explícito usa el de localhost, no el default de
boto3, que apuntaría a la cuenta real si hubiera credenciales en el entorno.
"""

from __future__ import annotations

import os
import uuid

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.persistence.dynamo import Dynamo, connect
from app.persistence.table import drop_table, ensure_table

# DynamoDB Local **en memoria** (`dynamodb-test` del compose), aparte del de desarrollo:
# el persistente fsynca cada escritura y sembrar tarda minutos; este, medio segundo. Además
# la suite nunca toca la tabla con tus datos. Dentro del contenedor `api` el endpoint viene en
# `DYNAMO_TEST_ENDPOINT_URL`; desde el host queda en el 8002.
ENDPOINT = os.environ.get("DYNAMO_TEST_ENDPOINT_URL") or "http://localhost:8002"


def clear_table(db: Dynamo) -> None:
    """Borra todos los ítems (claves, contadores, alias, todo) y deja la tabla lista.

    Es lo que hace barato aislar un test: crear y borrar una tabla con 4 GSIs en cada uno
    cuesta ~0.4 s y, peor, DynamoDB Local se va degradando con tantas altas y bajas (la suite
    llegó a tardar 3,5 veces más). Vaciar la misma tabla es una fracción de eso.
    """
    kwargs = {"ProjectionExpression": "PK, SK", "ConsistentRead": True}
    while True:
        page = db.table.scan(**kwargs)
        with db.table.batch_writer() as batch:
            for item in page["Items"]:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        if "LastEvaluatedKey" not in page:
            return
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def temporary_dynamo(*, create_table: bool):
    """Generador para fixtures: una tabla con nombre único, borrada al terminar.

    Falla (no se saltea) si no hay un DynamoDB al que conectarse: desde la fase 4 la API
    entera corre sobre DynamoDB, y una suite que se saltea sola en silencio sería una suite
    en verde que no probó nada.
    """
    handle: Dynamo = connect(
        f"bookup-test-{uuid.uuid4().hex[:12]}",
        endpoint_url=ENDPOINT,
        # DynamoDB Local acepta cualquier credencial, pero boto3 exige alguna.
        access_key_id="local",
        secret_access_key="local",
    )
    try:
        handle.client.list_tables(Limit=1)
    except (EndpointConnectionError, ClientError, OSError):
        pytest.fail(
            f"no DynamoDB reachable at {ENDPOINT}: run `docker compose up -d dynamodb-test` "
            "(or set DYNAMO_TEST_ENDPOINT_URL)",
            pytrace=False,
        )
    try:
        if create_table:
            ensure_table(handle)
        yield handle
    finally:
        drop_table(handle)
