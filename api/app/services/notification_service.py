"""Notificaciones: entrega de eventos a las bandejas (`notifications-roadmap.md` §5).

`deliver` es el lado del inbox-writer: recibe un evento ya detectado y escribe las dos
notificaciones (la del lector y la de la sede) con sus textos. Las operaciones de lectura de la
API (listar, contar, marcar) llegan con la fase 4.
"""

from __future__ import annotations

from datetime import timedelta

from ..config import settings
from ..notifications.events import ReservationEvent
from ..notifications.messages import Names, render
from ..persistence.dynamo import Dynamo
from ..persistence.entities import InboxKind, Notification
from ..persistence.errors import ConditionFailedError
from ..persistence.repositories import (
    BookRepository,
    LibraryRepository,
    NotificationRepository,
    UserRepository,
)


def deliver(
    db: Dynamo,
    event: ReservationEvent,
    *,
    retention_days: int | None = None,
    timezone: str | None = None,
) -> bool:
    """Escribe la notificación del lector y la de la sede de un evento, juntas.

    Idempotente: devuelve `False` (y no escribe nada) si el evento ya se había entregado, que
    es lo que pasa cuando SNS o Lambda lo reintentan. Si el lector ya no existe, entrega solo
    a la sede: la sede igual tiene que enterarse de lo que pasó con su ejemplar.
    """
    retention = settings.notifications_retention_days if retention_days is None else retention_days
    zone = timezone or settings.notifications_timezone
    r = event.reservation

    book = BookRepository(db).get(r.isbn)
    library = LibraryRepository(db).get(r.library_id)
    reader = UserRepository(db).get(r.user_id)
    texts = render(
        event,
        Names(
            # Un libro o una sede no se pueden borrar con ejemplares, así que siempre están;
            # el respaldo es para no perder el aviso si algún día eso cambia.
            book_title=book.title if book else r.isbn,
            library_name=library.name if library else f"la sede #{r.library_id}",
            reader_name=reader.name if reader else None,
        ),
        timezone=zone,
    )

    def notification(kind: InboxKind) -> Notification:
        return Notification(
            type=event.type.value,
            title=texts[kind].title,
            body=texts[kind].body,
            reservation_id=r.id,
            library_id=r.library_id,
            isbn=r.isbn,
            created_at=event.occurred_at,
            delete_after=event.occurred_at + timedelta(days=retention),
        )

    repo = NotificationRepository(db)
    library_entry = (InboxKind.library, r.library_id, notification(InboxKind.library))
    if reader is not None:
        try:
            return repo.deliver(
                [(InboxKind.user, r.user_id, notification(InboxKind.user)), library_entry],
                event.event_id,
                require_user=r.user_id,
            )
        except ConditionFailedError:
            pass  # el lector se borró entre la lectura y la escritura
    return repo.deliver([library_entry], event.event_id)
