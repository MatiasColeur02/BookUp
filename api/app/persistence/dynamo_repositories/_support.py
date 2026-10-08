"""Piezas compartidas por los repositories de DynamoDB.

Nada de esto es público fuera de `persistence/`. Cuatro responsabilidades:

- **Codec**: entidad (dataclass) ↔ ítem. Los `None` no se guardan —un atributo ausente
  *es* el null—, así que "abierta" es `attribute_not_exists(cancelled_at)`.
- **Ids**: el contador atómico que reemplaza al autoincremental de Postgres.
- **Lecturas**: paginar un Query completo, `BatchGetItem` con sus reintentos.
- **Transacciones**: armar los ítems de `TransactWriteItems` y traducir su cancelación.
"""

from __future__ import annotations

import dataclasses
import enum
import time
import typing
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Any, TypeVar

from botocore.exceptions import ClientError

from .. import keys
from ..dynamo import Dynamo
from ..errors import AlreadyExistsError, ConditionFailedError

E = TypeVar("E")

# TransactWriteItems admite hasta 100 ítems por llamada.
TRANSACTION_LIMIT = 100
# BatchGetItem, hasta 100 claves.
BATCH_GET_LIMIT = 100

_TRANSACTION_RETRIES = 6


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------


def _encode(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime):
        return keys.iso(value)
    return value


@lru_cache(maxsize=None)
def _decoders(cls: type) -> dict[str, Any]:
    """Para cada campo de la dataclass, cómo reconstruir su valor desde el ítem."""
    hints = typing.get_type_hints(cls)
    decoders: dict[str, Any] = {}
    for field in dataclasses.fields(cls):
        hint = hints[field.name]
        # `X | None` → X
        candidates = [a for a in typing.get_args(hint) if a is not type(None)] or [hint]
        target = candidates[0]
        if isinstance(target, type) and issubclass(target, enum.Enum):
            decoders[field.name] = target
        elif target is datetime:
            decoders[field.name] = lambda v: datetime.fromisoformat(v)
        elif target is int:
            decoders[field.name] = int  # DynamoDB devuelve Decimal
        else:
            decoders[field.name] = None
    return decoders


def to_item(entity: Any, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """Atributos propios de la entidad. Omite los `None` y lo que se pasa en `exclude`."""
    item: dict[str, Any] = {}
    for field in dataclasses.fields(entity):
        if field.name in exclude:
            continue
        value = getattr(entity, field.name)
        if value is not None:
            item[field.name] = _encode(value)
    return item


def from_item(cls: type[E], item: dict[str, Any], **overrides: Any) -> E:
    """Reconstruye una entidad ignorando los atributos de clave (`PK`, `GSI1PK`, ...)."""
    kwargs: dict[str, Any] = {}
    for name, decoder in _decoders(cls).items():
        if name in overrides:
            continue
        if name in item:
            value = item[name]
            kwargs[name] = decoder(value) if decoder is not None else value
    kwargs.update(overrides)
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Ids
# ---------------------------------------------------------------------------


def next_id(db: Dynamo, entity: str) -> int:
    """Siguiente id de una entidad. `ADD` es atómico en el servidor: dos altas
    concurrentes nunca obtienen el mismo número. Ver `ROADMAP.md` §4.1."""
    response = db.table.update_item(
        Key=keys.counter(entity),
        UpdateExpression="ADD seq :one",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(response["Attributes"]["seq"])


# ---------------------------------------------------------------------------
# Lecturas
# ---------------------------------------------------------------------------


def query_all(db: Dynamo, **kwargs: Any) -> list[dict[str, Any]]:
    """Todos los ítems de un Query, siguiendo `LastEvaluatedKey`."""
    items: list[dict[str, Any]] = []
    while True:
        response = db.table.query(**kwargs)
        items.extend(response["Items"])
        last = response.get("LastEvaluatedKey")
        if last is None:
            return items
        kwargs["ExclusiveStartKey"] = last


def exists_any(db: Dynamo, **kwargs: Any) -> bool:
    """¿El Query tiene al menos un resultado? Reemplaza a los `COUNT(*)` de los 409.

    Con `Limit=1`: contar en DynamoDB es recorrer, preguntar si hay uno no. OJO: `Limit`
    se aplica *antes* del `FilterExpression`, así que esto solo vale para Querys sin filtro.
    """
    assert "FilterExpression" not in kwargs
    return bool(db.table.query(Limit=1, Select="COUNT", **kwargs)["Count"])


def get_item(db: Dynamo, pk: str, sk: str = keys.META) -> dict[str, Any] | None:
    """GetItem con lectura fuerte: lo que se acaba de escribir se lee."""
    return db.table.get_item(Key=keys.key(pk, sk), ConsistentRead=True).get("Item")


def batch_get(db: Dynamo, key_list: list[dict[str, str]]) -> list[dict[str, Any]]:
    """BatchGetItem de claves distintas, de a 100 y reintentando las no procesadas."""
    unique = list({(k[keys.PK], k[keys.SK]): k for k in key_list}.values())
    found: list[dict[str, Any]] = []
    for start in range(0, len(unique), BATCH_GET_LIMIT):
        request = {db.table_name: {"Keys": unique[start : start + BATCH_GET_LIMIT], "ConsistentRead": True}}
        attempt = 0
        while request:
            response = db.resource.batch_get_item(RequestItems=request)
            found.extend(response["Responses"].get(db.table_name, []))
            request = response.get("UnprocessedKeys") or {}
            if request:
                attempt += 1
                time.sleep(min(0.05 * 2**attempt, 1))
    return found


# ---------------------------------------------------------------------------
# Transacciones
# ---------------------------------------------------------------------------


def tx_put(item: dict[str, Any], *, condition: str | None = None) -> dict[str, Any]:
    op: dict[str, Any] = {"Item": item}
    if condition:
        op["ConditionExpression"] = condition
    return {"Put": op}


def tx_update(
    key: dict[str, str],
    *,
    set_: dict[str, Any] | None = None,
    remove: tuple[str, ...] | list[str] = (),
    condition: str | None = None,
    names: dict[str, str] | None = None,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update con `SET`/`REMOVE` armados desde diccionarios.

    Los atributos de `set_` y `remove` se pasan por `#alias`: `status`, `name` y varios
    más son palabras reservadas de DynamoDB. `names`/`values` son para la `condition`.
    """
    expression_names = dict(names or {})
    expression_values = dict(values or {})
    set_parts, remove_parts = [], []
    for i, (attr, value) in enumerate((set_ or {}).items()):
        expression_names[f"#s{i}"] = attr
        expression_values[f":s{i}"] = _encode(value)
        set_parts.append(f"#s{i} = :s{i}")
    for i, attr in enumerate(remove):
        expression_names[f"#r{i}"] = attr
        remove_parts.append(f"#r{i}")

    expression = []
    if set_parts:
        expression.append("SET " + ", ".join(set_parts))
    if remove_parts:
        expression.append("REMOVE " + ", ".join(remove_parts))

    op: dict[str, Any] = {
        "Key": key,
        "UpdateExpression": " ".join(expression),
        "ExpressionAttributeNames": expression_names,
    }
    if expression_values:
        op["ExpressionAttributeValues"] = expression_values
    if condition:
        op["ConditionExpression"] = condition
    return {"Update": op}


def tx_delete(key: dict[str, str], *, condition: str | None = None) -> dict[str, Any]:
    op: dict[str, Any] = {"Key": key}
    if condition:
        op["ConditionExpression"] = condition
    return {"Delete": op}


def tx_check(key: dict[str, str], condition: str) -> dict[str, Any]:
    return {"ConditionCheck": {"Key": key, "ConditionExpression": condition}}


def _cancellation_codes(exc: ClientError) -> list[str]:
    return [r.get("Code", "None") for r in exc.response.get("CancellationReasons", [])]


def run_transaction(
    db: Dynamo,
    ops: list[dict[str, Any]],
    *,
    exists_error: str | None = None,
    failed_error: str = "A condition of the write was not met",
) -> None:
    """Ejecuta un `TransactWriteItems` y traduce su cancelación.

    - `ConditionalCheckFailed` → `ConditionFailedError` (el 409 del contrato). Si se pasa
      `exists_error` y el que falló es un `Put` (el de unicidad), `AlreadyExistsError`.
    - `TransactionConflict` es otra transacción tocando el mismo ítem *en ese instante*,
      no una condición no cumplida: se reintenta. Sin esto, dos reservas simultáneas del
      mismo ejemplar podrían dar una 409 y un 500 en lugar de 201 y 409.
    """
    # Cada operación de una transacción lleva su propio `TableName`; los builders `tx_*`
    # no lo conocen, así que se completa acá.
    items = [{kind: {**body, "TableName": db.table_name}} for op in ops for kind, body in op.items()]
    for attempt in range(_TRANSACTION_RETRIES):
        try:
            db.client.transact_write_items(TransactItems=items)
            return
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code != "TransactionCanceledException":
                raise
            codes = _cancellation_codes(exc)
            failed = [i for i, c in enumerate(codes) if c == "ConditionalCheckFailed"]
            if failed:
                if exists_error is not None and any("Put" in ops[i] for i in failed):
                    raise AlreadyExistsError(exists_error) from exc
                raise ConditionFailedError(failed_error) from exc
            if "TransactionConflict" in codes and attempt < _TRANSACTION_RETRIES - 1:
                time.sleep(0.01 * (attempt + 1))
                continue
            raise


def run_in_batches(
    db: Dynamo, ops: list[dict[str, Any]], *, size: int = TRANSACTION_LIMIT
) -> None:
    """Transacciones sucesivas para más de 100 operaciones. **No es atómico en conjunto**:
    cada lote lo es. Sirve para cascadas idempotentes (renombrar), no para invariantes."""
    for start in range(0, len(ops), size):
        run_transaction(db, ops[start : start + size])


def cascade_set(db: Dynamo, item_keys: list[dict[str, str]], attrs: dict[str, Any]) -> None:
    """Reescribe atributos desnormalizados en muchos ítems (`author_name`, `library_city`).

    Por lotes de 100, idempotente: si se corta a mitad, repetir la operación termina el
    trabajo. Un ítem que se borró en el medio se saltea en vez de resucitarlo.
    """
    for start in range(0, len(item_keys), TRANSACTION_LIMIT):
        chunk = item_keys[start : start + TRANSACTION_LIMIT]
        ops = [
            tx_update(
                k,
                set_=attrs,
                condition="attribute_exists(#pk)",
                names={"#pk": keys.PK},
            )
            for k in chunk
        ]
        try:
            run_transaction(db, ops)
        except ConditionFailedError:
            # Alguno se borró entre el Query y la escritura: ese lote se rehace uno a uno.
            for op in ops:
                try:
                    run_transaction(db, [op])
                except ConditionFailedError:
                    pass


def index_keys(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Claves primarias de ítems leídos de un GSI."""
    return [keys.key(i[keys.PK], i[keys.SK]) for i in items]
