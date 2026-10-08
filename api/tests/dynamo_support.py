"""Conexión a DynamoDB Local para los tests que la necesitan.

Nunca se conecta a AWS: sin endpoint explícito usa el de localhost, no el default de
boto3, que apuntaría a la cuenta real si hubiera credenciales en el entorno.
"""

from __future__ import annotations

import uuid

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.config import settings
from app.persistence.dynamo import Dynamo, connect
from app.persistence.table import drop_table, ensure_table

# Dentro del contenedor `api` el endpoint viene en `DYNAMO_ENDPOINT_URL`; desde el host,
# DynamoDB Local del compose queda en el 8001.
ENDPOINT = settings.dynamo_endpoint_url or "http://localhost:8001"


def temporary_dynamo(*, create_table: bool):
    """Generador para fixtures: una tabla con nombre único, borrada al terminar.

    Se saltea el test si no hay un DynamoDB al que conectarse, así la suite sigue
    corriendo sin Docker mientras la API esté sobre Postgres.
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
        pytest.skip(f"no DynamoDB reachable at {ENDPOINT}")
    try:
        if create_table:
            ensure_table(handle)
        yield handle
    finally:
        drop_table(handle)
