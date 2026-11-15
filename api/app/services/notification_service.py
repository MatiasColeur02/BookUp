"""Notificaciones: entrega de eventos a las bandejas (`notifications-roadmap.md` §5).

`deliver` es el lado del inbox-writer: recibe un evento ya detectado y escribe las dos
notificaciones (la del lector y la de la sede) con sus textos. El resto es el lado de la API:
listar, contar y marcar como leídas, con la autorización de §6.2.

**La bandeja sale del usuario, nunca del request.** `scope=me` es la del `viewer`, y
`scope=library` la de *su* sede (solo un librarian con sede). No hay parámetro `library_id` que
alguien pueda cambiar para leer la bandeja de otra; y como el `User` se recarga en cada request,
un librarian al que mueven de sede ve la nueva desde el request siguiente.
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta, timezone as tz

from ..config import settings
from ..notifications.events import ReservationEvent
from ..notifications.messages import Names, render
from ..persistence.dynamo import Dynamo
from ..persistence.entities import DeadlineKind, InboxKind, Notification, User, UserRole
from ..persistence.errors import ConditionFailedError
from ..persistence.repositories import (
    BookRepository,
    LibraryRepository,
    NotificationRepository,
    ReservationRepository,
    UserRepository,
)
from .errors import ForbiddenError, NotFoundError


class Scope(str, enum.Enum):
    me = "me"
    library = "library"


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


# ---------------------------------------------------------------------------
# Lado job (deadline-scanner)
# ---------------------------------------------------------------------------


def scan_deadlines(db: Dynamo, *, now: datetime | None = None) -> int:
    """Marca las reservas abiertas cuyo plazo venció y todavía no se avisó. Devuelve cuántas.

    No escribe notificaciones: la marca es una escritura más de la reserva, y el aviso sale
    por el stream como cualquier otro (§3.4). La condición de la marca es la idempotencia: dos
    corridas concurrentes avisan una sola vez, y una extensión que llega en el medio gana.
    """
    moment = now or datetime.now(tz.utc)
    repo = ReservationRepository(db)
    marked = 0
    for reservation in repo.list_past_due(moment):
        if reservation.picked_up:
            kind, already = DeadlineKind.return_, reservation.return_deadline_notified_at
        else:
            kind, already = DeadlineKind.pickup, reservation.pickup_deadline_notified_at
        if already is not None:
            continue  # ya avisada: ni siquiera vale el intento condicional
        try:
            repo.mark_deadline_notified(reservation.id, kind, reservation.expires_at, at=moment)
            marked += 1
        except ConditionFailedError:
            pass  # la cerraron, la retiraron, la extendieron u otra corrida la marcó
    return marked


# ---------------------------------------------------------------------------
# Lado API
# ---------------------------------------------------------------------------


def _library_inbox_id(viewer: User) -> int | None:
    """La sede cuya bandeja comparte el `viewer`, si tiene. Los sysadmin no tienen bandeja de
    sede (`notifications-roadmap.md` §0)."""
    if viewer.role is UserRole.librarian and viewer.library_id is not None:
        return viewer.library_id
    return None


def _inbox(viewer: User, scope: Scope) -> tuple[InboxKind, int]:
    if scope is Scope.me:
        return InboxKind.user, viewer.id
    library_id = _library_inbox_id(viewer)
    if library_id is None:
        raise ForbiddenError("Only a librarian assigned to a library has a library inbox")
    return InboxKind.library, library_id


def list_inbox(
    db: Dynamo,
    *,
    viewer: User,
    scope: Scope,
    limit: int = 20,
    cursor: str | None = None,
    now: datetime | None = None,
) -> tuple[list[Notification], str | None]:
    """Una página de la bandeja, de la más nueva a la más vieja, y el cursor de la siguiente.
    Un cursor que no salió de acá levanta `InvalidReferenceError` (422)."""
    kind, owner = _inbox(viewer, scope)
    return NotificationRepository(db).list(
        kind, owner, now=now or datetime.now(tz.utc), limit=limit, cursor=cursor
    )


def unread_counts(db: Dynamo, *, viewer: User) -> dict[str, int | None]:
    """`{"me": n, "library": m}`, con `library` en `None` si no tiene bandeja de sede. Dos
    `GetItem`: es lo que pregunta el polling cada 30 s."""
    repo = NotificationRepository(db)
    library_id = _library_inbox_id(viewer)
    return {
        "me": repo.unread_count(InboxKind.user, viewer.id),
        "library": None if library_id is None else repo.unread_count(InboxKind.library, library_id),
    }


def mark_read(db: Dynamo, *, viewer: User, scope: Scope, notification_id: str) -> Notification:
    """Idempotente: si ya estaba leída la devuelve como está, sin descontar otra vez."""
    kind, owner = _inbox(viewer, scope)
    notification = NotificationRepository(db).mark_read(
        kind, owner, notification_id, by=viewer.id, at=datetime.now(tz.utc)
    )
    if notification is None:
        raise NotFoundError("Notification not found")
    return notification


def mark_all_read(db: Dynamo, *, viewer: User, scope: Scope) -> int:
    kind, owner = _inbox(viewer, scope)
    return NotificationRepository(db).mark_all_read(kind, owner, by=viewer.id, at=datetime.now(tz.utc))
