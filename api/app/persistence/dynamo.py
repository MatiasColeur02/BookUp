"""Conexión a DynamoDB: el reemplazo de `database.py` (engine + `Session`).

`Dynamo` es lo que los services van a recibir como `db`, con la misma firma
`(db, *, ...)` que hoy. Junta lo que un repository necesita —el recurso de la tabla para
las operaciones de un ítem y el cliente de bajo nivel para `TransactWriteItems`— y no
expone nada de boto3 hacia afuera de `persistence/`.

Sin `DYNAMO_ENDPOINT_URL` se conecta a DynamoDB real, y las credenciales salen de la
cadena default de boto3 (el rol de la tarea en ECS), igual que `storage.py` con S3.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterator

import boto3
from botocore.config import Config

from ..config import settings


class DynamoDisabledError(RuntimeError):
    """No hay tabla configurada: falta `DYNAMO_TABLE`."""


@dataclass(frozen=True)
class Dynamo:
    table_name: str
    # Recurso de alto nivel: `Table` convierte tipos de Python (int, str) sin que haya
    # que escribir `{"N": "1"}` a mano. Lo usan las lecturas y las escrituras de un ítem.
    resource: Any
    table: Any
    # Cliente de bajo nivel: `TransactWriteItems` no existe en el recurso `Table`.
    client: Any
    # Lectura del stream de la tabla (`app/indexer.py`). Mismo endpoint y credenciales que
    # `client`: el stream de una tabla vive donde vive la tabla.
    streams: Any


def connect(
    table_name: str,
    *,
    endpoint_url: str = "",
    region: str = "us-east-1",
    access_key_id: str = "",
    secret_access_key: str = "",
) -> Dynamo:
    """Arma un `Dynamo` contra un endpoint y una tabla dados. No toca la red."""
    kwargs: dict[str, Any] = {
        "region_name": region,
        "endpoint_url": endpoint_url or None,
        # Un cliente reintentando en silencio esconde el problema detrás de latencia.
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    # Credenciales explícitas solo si están en el entorno; si no, la cadena de boto3.
    if access_key_id and secret_access_key:
        kwargs["aws_access_key_id"] = access_key_id
        kwargs["aws_secret_access_key"] = secret_access_key

    # Una `Session` propia y no el default de boto3: crear recursos desde varios threads
    # sobre la sesión compartida es una carrera conocida.
    session = boto3.session.Session()
    resource = session.resource("dynamodb", **kwargs)
    return Dynamo(
        table_name=table_name,
        resource=resource,
        table=resource.Table(table_name),
        client=resource.meta.client,
        streams=session.client("dynamodbstreams", **kwargs),
    )


_local = threading.local()


def get_dynamo() -> Dynamo:
    """El `Dynamo` de la app, armado desde `settings` una vez por thread.

    Los endpoints síncronos de FastAPI corren en un pool de threads, y los recursos de
    boto3 no son thread-safe (los clientes sí, pero el recurso `Table` no). Un `Dynamo`
    por thread evita compartirlos sin pagar una conexión nueva por request.
    """
    if not settings.dynamo_table:
        raise DynamoDisabledError("DYNAMO_TABLE is not set")
    dynamo = getattr(_local, "dynamo", None)
    if dynamo is None:
        dynamo = _local.dynamo = connect(
            settings.dynamo_table,
            endpoint_url=settings.dynamo_endpoint_url,
            region=settings.aws_region,
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
        )
    return dynamo


def get_db() -> Iterator[Dynamo]:
    """Dependencia de FastAPI. A diferencia de `Session` no hay nada que cerrar."""
    yield get_dynamo()
