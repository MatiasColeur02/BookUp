import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api";
import type { NotificationScope, UnreadCounts } from "../types";
import { useSession } from "./SessionContext";

/**
 * Los contadores de no leídas y el polling que los mantiene (`notifications-roadmap.md` §7.5).
 *
 * - Pregunta cada 30 s **solo con la pestaña visible**. Al volver a la pestaña o al foco,
 *   pregunta en el momento. Sin sesión no corre.
 * - Si falla, backoff (30 → 60 → 120 s, tope 5 min) y se conserva el último número. Un 401 ya
 *   lo resuelve el interceptor de `api.ts`: limpia el token, la sesión se cierra y esto se apaga.
 * - `refreshSoon()`: después de una acción propia (reservar, cancelar, retirar, devolver).
 *   La cadena stream → notificador → bandeja tarda unos segundos, y sin esto la notificación
 *   de lo que uno acaba de hacer llegaría recién en el próximo ciclo.
 */

const POLL_MS = 30_000;
const MAX_BACKOFF_MS = 5 * 60_000;
const SOON_MS = 3_000;
// El foco llega en ráfagas (cambiar de ventana dispara varios): no vale un request por cada uno.
const FOCUS_THROTTLE_MS = 5_000;

interface Notifications {
  /** `null` mientras no hay sesión o todavía no llegó la primera respuesta. */
  counts: UnreadCounts | null;
  /** `me + library`: lo que muestra el número rojo. */
  total: number;
  /**
   * Cambia solo cuando el **servidor** devuelve contadores distintos de los anteriores (no con
   * los ajustes optimistas): el panel abierto lo usa para saber que hay notificaciones nuevas.
   */
  serverVersion: number;
  refresh: () => void;
  refreshSoon: () => void;
  /** Ajuste optimista al marcar como leídas, antes de que conteste la API. */
  adjust: (scope: NotificationScope, delta: number) => void;
}

const NotificationsContext = createContext<Notifications | null>(null);

function sameCounts(a: UnreadCounts | null, b: UnreadCounts): boolean {
  return a !== null && a.me === b.me && a.library === b.library;
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const userId = user?.id ?? null;
  const [counts, setCounts] = useState<UnreadCounts | null>(null);
  const [serverVersion, setServerVersion] = useState(0);
  const lastServer = useRef<UnreadCounts | null>(null);
  // Los dos disparadores externos los arma el efecto, que es dueño del timer.
  const refreshRef = useRef<() => void>(() => undefined);
  const soonRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    lastServer.current = null;
    setCounts(null);
    if (userId === null) return;

    let stopped = false;
    let timer: number | undefined;
    let delay = POLL_MS;
    let inFlight = false;
    let lastFetch = 0;

    const visible = () => document.visibilityState === "visible";

    const schedule = (ms: number) => {
      window.clearTimeout(timer);
      timer = visible() ? window.setTimeout(tick, ms) : undefined;
    };

    async function tick() {
      if (stopped || inFlight) return;
      inFlight = true;
      lastFetch = Date.now();
      try {
        const next = await api.notifications.unreadCount();
        if (stopped) return;
        if (!sameCounts(lastServer.current, next)) setServerVersion((v) => v + 1);
        lastServer.current = next;
        setCounts(next);
        delay = POLL_MS;
      } catch {
        if (stopped) return;
        delay = Math.min(delay * 2, MAX_BACKOFF_MS);
      } finally {
        inFlight = false;
      }
      schedule(delay);
    }

    const onVisibility = () => {
      if (visible()) void tick();
      else window.clearTimeout(timer); // pestaña oculta: cero requests
    };
    const onFocus = () => {
      if (visible() && Date.now() - lastFetch > FOCUS_THROTTLE_MS) void tick();
    };

    refreshRef.current = () => void tick();
    soonRef.current = () => schedule(SOON_MS);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    if (visible()) void tick();

    return () => {
      stopped = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onFocus);
      refreshRef.current = () => undefined;
      soonRef.current = () => undefined;
    };
  }, [userId]);

  const refresh = useCallback(() => refreshRef.current(), []);
  const refreshSoon = useCallback(() => soonRef.current(), []);

  const adjust = useCallback((scope: NotificationScope, delta: number) => {
    setCounts((current) => {
      if (current === null) return current;
      if (scope === "library") {
        return current.library === null
          ? current
          : { ...current, library: Math.max(current.library + delta, 0) };
      }
      return { ...current, me: Math.max(current.me + delta, 0) };
    });
  }, []);

  const value = useMemo<Notifications>(
    () => ({
      counts,
      total: counts ? counts.me + (counts.library ?? 0) : 0,
      serverVersion,
      refresh,
      refreshSoon,
      adjust,
    }),
    [counts, serverVersion, refresh, refreshSoon, adjust]
  );

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}

export function useNotifications(): Notifications {
  const context = useContext(NotificationsContext);
  if (context === null) {
    throw new Error("useNotifications tiene que usarse dentro de <NotificationsProvider>");
  }
  return context;
}
