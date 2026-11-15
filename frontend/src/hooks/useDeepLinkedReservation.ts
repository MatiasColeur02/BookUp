import { useEffect, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { RESERVATION_PARAM } from "../lib/notifications";
import type { Reservation } from "../types";

/** El `id` del `<tr>` de una reserva, para poder hacer scroll hasta ella. */
export function reservationRowId(reservationId: number): string {
  return `reserva-${reservationId}`;
}

/** La reserva que pide la URL (`?reserva=<id>`), o `null`. */
export function useRequestedReservation(): number | null {
  const [params] = useSearchParams();
  const id = Number(params.get(RESERVATION_PARAM));
  return Number.isInteger(id) && id > 0 ? id : null;
}

/**
 * El deep link de una notificación (`notifications-roadmap.md` §7.4): cuando la reserva
 * pedida aparece en el listado, hace scroll hasta su fila y la resalta unos segundos.
 * Devuelve la reserva resaltada. Cada navegación (`location.key`) cuenta una sola vez: volver a
 * clickear la misma notificación vuelve a llevar a la fila.
 */
export function useDeepLinkedReservation(reservations: Reservation[], loading: boolean): number | null {
  const requested = useRequestedReservation();
  const location = useLocation();
  const handled = useRef<string | null>(null);
  const [highlighted, setHighlighted] = useState<number | null>(null);

  useEffect(() => {
    if (requested === null || loading || handled.current === location.key) return;
    if (!reservations.some((reservation) => reservation.id === requested)) return;
    handled.current = location.key;
    setHighlighted(requested);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Después del render que pinta el resaltado.
    requestAnimationFrame(() =>
      document
        .getElementById(reservationRowId(requested))
        ?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" })
    );
  }, [requested, loading, reservations, location.key]);

  useEffect(() => {
    if (highlighted === null) return;
    const timer = window.setTimeout(() => setHighlighted(null), 3000);
    return () => window.clearTimeout(timer);
  }, [highlighted]);

  return highlighted;
}
