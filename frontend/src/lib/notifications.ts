import type { ComponentType } from "react";
import {
  AlertIcon,
  BookIcon,
  CheckIcon,
  ClockIcon,
  HandoffIcon,
  XIcon,
} from "../components/icons";
import type { NotificationScope, NotificationType } from "../types";

/**
 * Cómo se presenta cada tipo de notificación (`notifications-roadmap.md` §7.4). El texto
 * ya viene armado del backend; acá solo se decide ícono, tono y adónde lleva el click.
 */

export type NotificationTone = "accent" | "success" | "neutral" | "warning" | "danger";

interface TypeStyle {
  tone: NotificationTone;
  Icon: ComponentType<{ className?: string }>;
}

const STYLES: Record<NotificationType, TypeStyle> = {
  "reservation.created": { tone: "accent", Icon: BookIcon },
  "reservation.picked_up": { tone: "success", Icon: HandoffIcon },
  "reservation.returned": { tone: "success", Icon: CheckIcon },
  "reservation.cancelled": { tone: "neutral", Icon: XIcon },
  "reservation.pickup_expired": { tone: "warning", Icon: ClockIcon },
  "reservation.return_overdue": { tone: "danger", Icon: AlertIcon },
};

const FALLBACK: TypeStyle = { tone: "neutral", Icon: BookIcon };

/** Un tipo que el frontend todavía no conoce se muestra neutro, no rompe la lista. */
export function styleOf(type: string): TypeStyle {
  return STYLES[type as NotificationType] ?? FALLBACK;
}

/** Parámetro de la URL con el que las dos pantallas de reservas reciben el deep link. */
export const RESERVATION_PARAM = "reserva";

/** Mi bandeja lleva a «Mis reservas»; la de la sede, al panel bibliotecario. */
export function destinationOf(scope: NotificationScope, reservationId: number): string {
  const path = scope === "me" ? "/mis-reservas" : "/panel";
  return `${path}?${RESERVATION_PARAM}=${reservationId}`;
}

/** El número rojo: nada con 0, «9+» desde 10. */
export function formatBadge(count: number): string | null {
  if (count <= 0) return null;
  return count > 9 ? "9+" : String(count);
}

const relative = new Intl.RelativeTimeFormat("es", { numeric: "auto" });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** «hace 5 minutos», «ayer», «hace 2 semanas». Menos de un minuto es «ahora». */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.trunc(seconds / size), unit);
  }
  return "ahora";
}

/** La fecha completa, para el `title` de la hora relativa. */
export function fullDate(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", { dateStyle: "long", timeStyle: "short" });
}
