"""Exportador de analítica: DynamoDB → S3 (JSON Lines), para consultar con Athena.

    handler: app.analytics.exporter.handler

Los reportes (reservas por sede y mes, libros más pedidos, cancelaciones...) no se hacen sobre
DynamoDB —no sabe agrupar— ni sobre la API: se hacen aparte, sobre una **foto** de los datos en
S3, sin cargar la app. Cada corrida reescribe tres archivos planos:

    reservations/reservations.jsonl   una fila por reserva (el hecho), con la sede y el estado
    libraries/libraries.jsonl         una fila por sede (la dimensión)
    books/books.jsonl                 una fila por libro del catálogo (la dimensión)

Es una foto completa y no un incremental: las reservas nunca se borran (el historial es la
gracia), así que reescribir todo es idempotente y no deja duplicados que Athena sume dos veces.
Se lee por los índices de lista (GSI1), sin `Scan` de la tabla. No se exporta nada personal: la
reserva lleva el `user_id`, no el email ni el nombre.

En AWS la dispara una rule de EventBridge; también se puede invocar a mano (ver el output
`analytics_export_command` de Terraform).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import boto3

from ..config import settings
from ..persistence import keys
from ..persistence.dynamo import Dynamo, get_dynamo
from ..persistence.entities import Library, Reservation
from ..persistence.repositories import LibraryRepository, ReservationRepository
from ..persistence.repositories import _support as s

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RESERVATIONS_KEY = "reservations/reservations.jsonl"
LIBRARIES_KEY = "libraries/libraries.jsonl"
BOOKS_KEY = "books/books.jsonl"


def _day(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if moment else None


def reservation_status(reservation: Reservation) -> str:
    """El estado final de una reserva en una sola palabra, para agrupar.

    Abierta: `reserved` (a retirar) o `loaned` (retirada, sin devolver). Cerrada: el motivo
    (`returned`, `cancelled`, `expired`, `lost`); una reserva anterior a `close_reason` cae a lo
    que dicen sus fechas."""
    if reservation.is_open:
        return "loaned" if reservation.picked_up else "reserved"
    if reservation.close_reason is not None:
        return reservation.close_reason.value
    return "returned" if reservation.returned_at else "cancelled"


def reservation_row(reservation: Reservation, libraries: dict[int, Library]) -> dict[str, Any]:
    library = libraries.get(reservation.library_id) if reservation.library_id else None
    reserved_at = reservation.reserved_at
    return {
        "reservation_id": reservation.id,
        "user_id": reservation.user_id,
        "physical_book_id": reservation.physical_book_id,
        "isbn": reservation.isbn,
        "library_id": reservation.library_id,
        "library_name": library.name if library else None,
        "library_city": library.city if library else None,
        "library_state": library.state if library else None,
        "status": reservation_status(reservation),
        "picked_up": reservation.picked_up,
        # `YYYY-MM`: lo que se agrupa en "reservas por mes", sin parsear fechas en SQL.
        "reserved_month": reserved_at.astimezone(timezone.utc).strftime("%Y-%m") if reserved_at else None,
        "reserved_at": _day(reserved_at),
        "expires_at": _day(reservation.expires_at),
        "picked_up_at": _day(reservation.picked_up_at),
        "returned_at": _day(reservation.returned_at),
        "cancelled_at": _day(reservation.cancelled_at),
        "cancelled_by": reservation.cancelled_by.value if reservation.cancelled_by else None,
    }


def library_row(library: Library) -> dict[str, Any]:
    return {
        "library_id": library.id,
        "name": library.name,
        "city": library.city,
        "state": library.state,
    }


def book_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "isbn": item["isbn"],
        "title": item["title"],
        "language": item.get("language"),
        "pages": int(item["pages"]) if item.get("pages") is not None else None,
    }


def _books(db: Dynamo) -> list[dict[str, Any]]:
    items = s.query_all(
        db,
        IndexName=keys.GSI1,
        KeyConditionExpression="GSI1PK = :list",
        ExpressionAttributeValues={":list": keys.LIST_CATALOG},
    )
    return [book_row(i) for i in items]


def build(db: Dynamo) -> dict[str, list[dict[str, Any]]]:
    """Las tres tablas planas, leídas de DynamoDB. Puro respecto de S3: se prueba sin AWS."""
    libraries = LibraryRepository(db).list_all()
    by_id = {lib.id: lib for lib in libraries}
    reservations = ReservationRepository(db).list_all()
    return {
        RESERVATIONS_KEY: [reservation_row(r, by_id) for r in reservations],
        LIBRARIES_KEY: [library_row(lib) for lib in libraries],
        BOOKS_KEY: _books(db),
    }


def to_jsonl(rows: Iterable[dict[str, Any]]) -> bytes:
    """Una fila por línea, sin comas ni corchetes: lo que lee el SerDe JSON de Athena."""
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows).encode()


def export(db: Dynamo, s3: Any, bucket: str) -> dict[str, int]:
    """Escribe la foto en el bucket. Devuelve cuántas filas quedó en cada archivo."""
    counts: dict[str, int] = {}
    for key, rows in build(db).items():
        s3.put_object(Bucket=bucket, Key=key, Body=to_jsonl(rows), ContentType="application/x-ndjson")
        counts[key] = len(rows)
    return counts


def handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, int]:
    if not settings.analytics_bucket:
        raise RuntimeError("ANALYTICS_BUCKET is not set")
    counts = export(get_dynamo(), boto3.client("s3", region_name=settings.s3_region), settings.analytics_bucket)
    logger.info("analytics export: %s", counts)
    return counts
