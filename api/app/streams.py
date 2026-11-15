"""Lectura local del stream de la tabla: lo que en AWS hace un *event source mapping*.

En AWS, Lambda lee el stream de DynamoDB sola y le pasa los registros al handler. En local no
hay quien lo haga, así que `follow()` lee el stream de DynamoDB Local y le pasa los **mismos**
registros a la misma función. Lo usan los dos lectores del stream: el indexador
(`app/indexer.py`) y el notificador (`app/notifications/local.py`).

No es una librería de consumo: no hay checkpoint persistente. Al arrancar (o cuando la tabla se
recrea) se engancha al **final** del stream; cada lector decide qué hacer con lo que pasó
mientras no estaba (el indexador reindexa todo; el notificador lo da por perdido).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from botocore.exceptions import ClientError

from .persistence.dynamo import Dynamo

logger = logging.getLogger(__name__)

Records = list[dict[str, Any]]


class StreamReader:
    """Lee el stream de la tabla shard por shard, recordando dónde quedó cada uno."""

    def __init__(self, db: Dynamo, *, start: str = "LATEST"):
        self.db = db
        self.start = start
        self.client = db.streams
        table = db.client.describe_table(TableName=db.table_name)["Table"]
        self.stream_arn = table["LatestStreamArn"]
        self.iterators: dict[str, str | None] = {}
        self.refresh_shards()

    def is_current(self) -> bool:
        """¿Sigue siendo éste el stream de la tabla? Falso si la tabla se borró y se recreó:
        DynamoDB Local no avisa con un error, simplemente el stream viejo deja de recibir."""
        table = self.db.client.describe_table(TableName=self.db.table_name)["Table"]
        return table.get("LatestStreamArn") == self.stream_arn

    def refresh_shards(self) -> None:
        """Toma los shards que todavía no se están leyendo. El primero arranca en `start`;
        los que aparecen después (hijos de uno que se cerró) arrancan desde su principio."""
        shards = self.client.describe_stream(StreamArn=self.stream_arn)["StreamDescription"]["Shards"]
        first = not self.iterators
        for shard in shards:
            shard_id = shard["ShardId"]
            if shard_id in self.iterators:
                continue
            self.iterators[shard_id] = self.client.get_shard_iterator(
                StreamArn=self.stream_arn,
                ShardId=shard_id,
                ShardIteratorType=self.start if first else "TRIM_HORIZON",
            )["ShardIterator"]

    def read(self) -> Records:
        """Los registros nuevos de todos los shards, sin bloquear."""
        records: Records = []
        for shard_id, iterator in list(self.iterators.items()):
            if iterator is None:
                continue
            while iterator:
                page = self.client.get_records(ShardIterator=iterator, Limit=100)
                records.extend(page["Records"])
                iterator = page.get("NextShardIterator")
                if not page["Records"]:
                    break
            self.iterators[shard_id] = iterator
        return records


# Errores que dicen que el stream que se estaba leyendo ya no existe o no se puede retomar:
# la tabla se borró y se recreó (`docker compose` + reset del seed), o el iterador venció.
STREAM_LOST = {"ResourceNotFoundException", "ExpiredIteratorException", "TrimmedDataAccessException"}


def follow(
    db: Dynamo,
    on_records: Callable[[Records], Any],
    *,
    on_attach: Callable[[], Any] | None = None,
    name: str = "stream",
    poll_seconds: float = 1.0,
) -> None:
    """Sigue el stream para siempre y le pasa cada lote no vacío a `on_records`.

    `on_attach` corre cada vez que se engancha un stream (al arrancar y cuando la tabla se
    recrea), **después** de tomar el iterador al final: lo que se escriba mientras corre queda
    en el stream y se procesa a continuación. Al revés, se perdería lo ocurrido en el medio.

    Nunca se cae: un error de un lote se loguea y se reintenta en la vuelta siguiente.
    """

    def attach() -> StreamReader:
        reader = StreamReader(db)
        if on_attach is not None:
            on_attach()
        logger.info("%s: following the stream of %s", name, db.table_name)
        return reader

    reader: StreamReader | None = None
    last_refresh = time.monotonic()
    while True:
        try:
            if reader is None:
                reader = attach()
            records = reader.read()
            if records:
                on_records(records)
            if time.monotonic() - last_refresh > 10:
                if reader.is_current():
                    reader.refresh_shards()
                else:
                    logger.warning("%s: the table was recreated (new stream); starting over", name)
                    reader = None
                last_refresh = time.monotonic()
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in STREAM_LOST:
                logger.warning("%s: the stream is gone (%s); starting over", name, code)
                reader = None  # la tabla puede no estar todavía: `attach` se reintenta
            else:
                logger.exception("%s: iteration failed; retrying", name)
        except Exception:  # noqa: BLE001 — el poller no se cae por un evento o un corte de red
            logger.exception("%s: iteration failed; retrying", name)
        time.sleep(poll_seconds)
