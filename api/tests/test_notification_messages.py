"""Los textos de las notificaciones (`notifications-roadmap.md` §2). Puros, sin base."""

from datetime import datetime, timezone

import pytest

from app.notifications.events import Actor, EventType, ReservationEvent
from app.notifications.messages import Names, format_date, render
from app.persistence.entities import CloseReason, InboxKind, Reservation

BA = "America/Argentina/Buenos_Aires"
# Fin del día 20/11 en Buenos Aires: en UTC ya es 21/11.
EXPIRES = datetime(2026, 11, 21, 2, 59, 59, tzinfo=timezone.utc)
NAMES = Names(book_title="Rayuela", library_name="Biblioteca Sur", reader_name="Ana Pérez")


def event(type_, actor=Actor.system, close_reason=None, names=NAMES):
    reservation = Reservation(
        id=123, user_id=7, library_id=3, physical_book_id=55, isbn="9788437604572",
        expires_at=EXPIRES, close_reason=close_reason,
    )
    e = ReservationEvent(type=type_, occurred_at=EXPIRES, actor=actor, reservation=reservation)
    texts = render(e, names, timezone=BA)
    return texts[InboxKind.user], texts[InboxKind.library]


def test_dates_are_written_in_the_networks_timezone():
    assert format_date(EXPIRES, BA) == "20/11"
    assert format_date(EXPIRES, "UTC") == "21/11"


@pytest.mark.parametrize(
    "type_, user, library",
    [
        (
            EventType.created,
            ("Reserva confirmada", "Reservaste «Rayuela» en Biblioteca Sur. Tenés hasta el 20/11 para retirarlo."),
            ("Nueva reserva", "Ana Pérez reservó «Rayuela» (ejemplar #55). Retiro hasta el 20/11."),
        ),
        (
            EventType.picked_up,
            ("Préstamo iniciado", "Retiraste «Rayuela». Devolvelo en Biblioteca Sur antes del 20/11."),
            ("Ejemplar entregado", "Se entregó «Rayuela» (ej. #55) a Ana Pérez. Vence el 20/11."),
        ),
        (
            EventType.return_overdue,
            ("Préstamo vencido", "El plazo para devolver «Rayuela» venció el 20/11. Devolvelo en Biblioteca Sur cuanto antes."),
            ("Préstamo en mora", "Ana Pérez no devolvió «Rayuela» (ej. #55); venció el 20/11."),
        ),
        (
            EventType.returned,
            ("Devolución registrada", "Biblioteca Sur registró la devolución de «Rayuela». ¡Gracias!"),
            ("Ejemplar devuelto", "Ana Pérez devolvió «Rayuela» (ej. #55): vuelve a estar disponible."),
        ),
    ],
)
def test_the_texts_of_the_roadmap(type_, user, library):
    u, l = event(type_)
    assert (u.title, u.body) == user
    assert (l.title, l.body) == library


@pytest.mark.parametrize(
    "actor, reason, user_body, library_body",
    [
        (Actor.user, CloseReason.cancelled, "Cancelaste tu reserva de «Rayuela».",
         "Ana Pérez canceló la reserva de «Rayuela» (ej. #55)."),
        (Actor.library, CloseReason.cancelled, "Biblioteca Sur canceló tu reserva de «Rayuela».",
         "Se canceló la reserva de Ana Pérez de «Rayuela» (ej. #55)."),
        (Actor.library, CloseReason.lost,
         "Biblioteca Sur canceló tu reserva de «Rayuela»: el ejemplar ya no está disponible.",
         "Se canceló la reserva de Ana Pérez de «Rayuela» (ej. #55): el ejemplar se marcó como perdido."),
    ],
)
def test_the_cancellation_variants(actor, reason, user_body, library_body):
    u, l = event(EventType.cancelled, actor, reason)
    assert u.title == l.title == "Reserva cancelada"
    assert (u.body, l.body) == (user_body, library_body)


def test_an_expired_pickup_tells_the_library_what_it_can_do_while_it_is_still_reserved():
    u, l = event(EventType.pickup_expired)
    assert u.title == "Venció el plazo de retiro"
    assert u.body == "No retiraste «Rayuela» antes del 20/11. Consultá con Biblioteca Sur si podés extenderlo."
    assert l.title == "Retiro vencido"
    assert "sigue reservado hasta que extiendas el plazo" in l.body


def test_an_expired_pickup_that_was_already_closed_says_the_copy_is_free():
    _, l = event(EventType.pickup_expired, close_reason=CloseReason.expired)
    assert l.body.endswith("La reserva se venció y el ejemplar volvió a estar disponible.")
    assert "sigue reservado" not in l.body


def test_a_deleted_reader_is_still_named_in_the_library_text():
    _, l = event(EventType.returned, names=Names(book_title="Rayuela", library_name="Sur", reader_name=None))
    assert l.body.startswith("Un lector devolvió «Rayuela»")
