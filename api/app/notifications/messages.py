"""Los textos de las notificaciones, en castellano (`notifications-roadmap.md` §2).

Se arman **al escribir** la notificación, no al leerla: así un canal futuro (email) reutiliza
el mismo texto, y la notificación conserva los nombres de entonces aunque después se renombre
el libro o la sede. Las fechas se guardan en UTC y se escriben en la zona de la red
(`NOTIFICATIONS_TIMEZONE`): `expires_at` llega como fin del día local, y en UTC un vencimiento
del 20/11 a las 23:59 de Buenos Aires ya es 21/11.

Funciones puras: reciben el evento y los nombres ya resueltos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..persistence.entities import CloseReason, InboxKind
from .events import Actor, EventType, ReservationEvent

# Si el lector se borró, la sede igual recibe la notificación.
UNKNOWN_READER = "Un lector"


@dataclass(frozen=True)
class Text:
    title: str
    body: str


@dataclass(frozen=True, kw_only=True)
class Names:
    """Lo que el texto necesita y el evento no trae (lleva ids, no nombres)."""

    book_title: str
    library_name: str
    reader_name: str | None


def format_date(moment: datetime, timezone: str) -> str:
    """`20/11`, en la zona de la red."""
    return moment.astimezone(ZoneInfo(timezone)).strftime("%d/%m")


def render(event: ReservationEvent, names: Names, *, timezone: str) -> dict[InboxKind, Text]:
    """El texto para la bandeja del lector y para la de la sede."""
    r = event.reservation
    book = f"«{names.book_title}»"
    lib = names.library_name
    reader = names.reader_name or UNKNOWN_READER
    copy = f"ej. #{r.physical_book_id}"
    date = format_date(r.expires_at, timezone)

    match event.type:
        case EventType.created:
            return {
                InboxKind.user: Text(
                    "Reserva confirmada",
                    f"Reservaste {book} en {lib}. Tenés hasta el {date} para retirarlo.",
                ),
                InboxKind.library: Text(
                    "Nueva reserva",
                    f"{reader} reservó {book} (ejemplar #{r.physical_book_id}). Retiro hasta el {date}.",
                ),
            }
        case EventType.picked_up:
            return {
                InboxKind.user: Text(
                    "Préstamo iniciado", f"Retiraste {book}. Devolvelo en {lib} antes del {date}."
                ),
                InboxKind.library: Text(
                    "Ejemplar entregado", f"Se entregó {book} ({copy}) a {reader}. Vence el {date}."
                ),
            }
        case EventType.cancelled:
            if r.close_reason is CloseReason.lost:
                user_body = f"{lib} canceló tu reserva de {book}: el ejemplar ya no está disponible."
                library_body = (
                    f"Se canceló la reserva de {reader} de {book} ({copy}): "
                    "el ejemplar se marcó como perdido."
                )
            elif event.actor is Actor.user:
                user_body = f"Cancelaste tu reserva de {book}."
                library_body = f"{reader} canceló la reserva de {book} ({copy})."
            else:
                user_body = f"{lib} canceló tu reserva de {book}."
                library_body = f"Se canceló la reserva de {reader} de {book} ({copy})."
            return {
                InboxKind.user: Text("Reserva cancelada", user_body),
                InboxKind.library: Text("Reserva cancelada", library_body),
            }
        case EventType.pickup_expired:
            if r.close_reason is CloseReason.expired:
                # Lo venció «vencer reservas» antes de que pasara el job: ya no está reservado.
                library_tail = "La reserva se venció y el ejemplar volvió a estar disponible."
            else:
                library_tail = (
                    "El ejemplar sigue reservado hasta que extiendas el plazo, la canceles "
                    "o corra el vencimiento."
                )
            return {
                InboxKind.user: Text(
                    "Venció el plazo de retiro",
                    f"No retiraste {book} antes del {date}. "
                    f"Consultá con {lib} si podés extenderlo.",
                ),
                InboxKind.library: Text(
                    "Retiro vencido",
                    f"{reader} no retiró {book} ({copy}) antes del {date}. {library_tail}",
                ),
            }
        case EventType.return_overdue:
            return {
                InboxKind.user: Text(
                    "Préstamo vencido",
                    f"El plazo para devolver {book} venció el {date}. Devolvelo en {lib} cuanto antes.",
                ),
                InboxKind.library: Text(
                    "Préstamo en mora", f"{reader} no devolvió {book} ({copy}); venció el {date}."
                ),
            }
        case EventType.returned:
            return {
                InboxKind.user: Text(
                    "Devolución registrada", f"{lib} registró la devolución de {book}. ¡Gracias!"
                ),
                InboxKind.library: Text(
                    "Ejemplar devuelto",
                    f"{reader} devolvió {book} ({copy}): vuelve a estar disponible.",
                ),
            }
    raise ValueError(f"No text for {event.type}")
