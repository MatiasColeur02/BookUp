import { isOpen } from "../lib/reservations";
import type { Reservation } from "../types";

export type ReservationState = "reserved" | "expired" | "picked_up" | "returned" | "cancelled";

interface StateInfo {
  label: string;
  className: string;
}

const STATES: Record<ReservationState, StateInfo> = {
  reserved: { label: "Reservada", className: "status-pending" },
  expired: { label: "Vencida", className: "status-cancelled" },
  picked_up: { label: "Retirada", className: "status-confirmed" },
  returned: { label: "Devuelta", className: "status-fulfilled" },
  cancelled: { label: "Cancelada", className: "status-cancelled" },
};

/**
 * La API no expone un enum de estado: se deriva de las tres columnas del ciclo de
 * vida. El orden de los chequeos importa — `cancelled_at`/`returned_at` mandan sobre
 * `picked_up`, porque una reserva cerrada ya no está retirada.
 *
 * "Vencida" no es un estado del backend: es una reserva **abierta** cuyo `expires_at`
 * ya pasó y que nadie retiró. Sigue reteniendo el ejemplar hasta que alguien la cierre
 * (a mano, o con `POST /reservations/expire`).
 */
export function reservationState(reservation: Reservation, now: Date = new Date()): ReservationState {
  if (reservation.cancelled_at !== null) return "cancelled";
  if (reservation.returned_at !== null) return "returned";
  if (reservation.picked_up) return "picked_up";
  return new Date(reservation.expires_at) < now ? "expired" : "reserved";
}

/** Una reserva abierta y sin retirar todavía se puede cancelar. */
export function canBeCancelled(reservation: Reservation): boolean {
  return isOpen(reservation) && !reservation.picked_up;
}

export function ReservationStatusBadge({ reservation }: { reservation: Reservation }) {
  const { label, className } = STATES[reservationState(reservation)];
  return <span className={`status-badge ${className}`}>{label}</span>;
}
