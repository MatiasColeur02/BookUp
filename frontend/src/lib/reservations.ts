import type { Reservation } from "../types";

export type OpenFilter = "open" | "closed" | "all";

export const OPEN_FILTERS: { value: OpenFilter; label: string }[] = [
  { value: "open", label: "Abiertas" },
  { value: "closed", label: "Cerradas" },
  { value: "all", label: "Todas" },
];

/** Ver el comentario de `Reservation` en `types.ts`: no hay un enum de estado. */
export function isOpen(reservation: Reservation): boolean {
  return reservation.cancelled_at === null && reservation.returned_at === null;
}

/**
 * En mora: sigue abierta y el vencimiento ya pasó. Es lo que el bibliotecario tiene que
 * ver de un vistazo — la API no lo marca, sale de comparar `expires_at` con ahora.
 */
export function isOverdue(reservation: Reservation): boolean {
  return isOpen(reservation) && new Date(reservation.expires_at) < new Date();
}

/** Traduce el filtro de la UI al `is_open` que espera `GET /reservations`. */
export function isOpenParam(filter: OpenFilter): boolean | undefined {
  if (filter === "open") return true;
  if (filter === "closed") return false;
  return undefined;
}
