import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useConfirm } from "../context/ConfirmContext";
import { useNotifications } from "../context/NotificationsContext";
import { useToast } from "../context/ToastContext";
import { destinationOf } from "../lib/notifications";
import type { Notification, NotificationScope } from "../types";
import { ErrorBanner } from "./ErrorBanner";
import { NotificationItem } from "./NotificationItem";

const PAGE_SIZE = 20;

interface Props {
  /** El usuario tiene bandeja de sede (un librarian con sede): muestra las dos pestañas. */
  hasLibraryInbox: boolean;
  onClose: () => void;
}

/**
 * El desplegable de la campana (`notifications-roadmap.md` §7.4). Abrirlo **no** marca nada:
 * el número baja solo al clickear cada notificación o con «Marcar todas como leídas».
 */
export function NotificationPanel({ hasLibraryInbox, onClose }: Props) {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();
  const { counts, serverVersion, adjust, refresh } = useNotifications();
  // Un librarian abre en «Sede»: es su trabajo.
  const [scope, setScope] = useState<NotificationScope>(hasLibraryInbox ? "library" : "me");
  const [items, setItems] = useState<Notification[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Descarta la respuesta de una pestaña que ya no está a la vista.
  const request = useRef(0);

  const loadFirstPage = useCallback(async (quiet: boolean) => {
    const id = ++request.current;
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const page = await api.notifications.list(scope, { limit: PAGE_SIZE });
      if (id !== request.current) return;
      setItems(page.items);
      setCursor(page.next_cursor);
    } catch (err) {
      if (id === request.current) setError(err);
    } finally {
      if (id === request.current) setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    void loadFirstPage(false);
  }, [loadFirstPage]);

  // Llegó algo nuevo mientras está abierto: se refresca sin volver al skeleton.
  const seenVersion = useRef(serverVersion);
  useEffect(() => {
    if (seenVersion.current === serverVersion) return;
    seenVersion.current = serverVersion;
    void loadFirstPage(true);
  }, [serverVersion, loadFirstPage]);

  const loadMore = async () => {
    if (cursor === null) return;
    setLoadingMore(true);
    try {
      const page = await api.notifications.list(scope, { limit: PAGE_SIZE, cursor });
      setItems((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch (err) {
      toast.error(err);
    } finally {
      setLoadingMore(false);
    }
  };

  const open = (notification: Notification) => {
    if (notification.read_at === null) {
      // Optimista: baja el número al instante y se revierte si la API falla.
      const now = new Date().toISOString();
      const setRead = (readAt: string | null) =>
        setItems((current) =>
          current.map((n) => (n.id === notification.id ? { ...n, read_at: readAt } : n))
        );
      setRead(now);
      adjust(scope, -1);
      api.notifications.markRead(scope, notification.id).catch((err) => {
        setRead(null);
        adjust(scope, 1);
        toast.error(err);
      });
    }
    onClose();
    navigate(destinationOf(scope, notification.reservation_id));
  };

  const markAll = async () => {
    if (scope === "library") {
      const confirmed = await confirm({
        tone: "positive",
        title: "Marcar todas como leídas",
        message: "La bandeja de la sede es compartida: quedan leídas para todo el personal de la sede.",
        confirmLabel: "Marcar todas",
        cancelLabel: "Volver",
      });
      if (!confirmed) return;
    }
    setMarkingAll(true);
    try {
      await api.notifications.markAllRead(scope);
      const now = new Date().toISOString();
      setItems((current) => current.map((n) => (n.read_at ? n : { ...n, read_at: now })));
      refresh();
    } catch (err) {
      toast.error(err);
    } finally {
      setMarkingAll(false);
    }
  };

  const unreadIn = (s: NotificationScope) => (s === "me" ? counts?.me : counts?.library) ?? 0;
  const tabLabel = (s: NotificationScope, label: string) =>
    unreadIn(s) > 0 ? `${label} · ${unreadIn(s)}` : label;

  return (
    <div className="notif-panel" role="dialog" aria-label="Notificaciones">
      <div className="notif-panel-header">
        <h2 className="notif-panel-title">Notificaciones</h2>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={markAll}
          disabled={markingAll || unreadIn(scope) === 0}
        >
          {markingAll ? "Marcando..." : "Marcar todas como leídas"}
        </button>
      </div>

      {hasLibraryInbox && (
        <div className="segmented segmented-sm notif-tabs">
          {(
            [
              ["me", "Mías"],
              ["library", "Sede"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={scope === value ? "active" : ""}
              aria-pressed={scope === value}
              onClick={() => setScope(value)}
            >
              {tabLabel(value, label)}
            </button>
          ))}
        </div>
      )}

      <div className="notif-panel-body">
        {loading ? (
          <div aria-hidden="true" className="notif-skeleton">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="skeleton skeleton-row" />
            ))}
          </div>
        ) : error ? (
          <div className="notif-error">
            <ErrorBanner error={error} />
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => loadFirstPage(false)}>
              Reintentar
            </button>
          </div>
        ) : items.length === 0 ? (
          <p className="empty notif-empty">No tenés notificaciones.</p>
        ) : (
          <>
            <ul className="notif-list">
              {items.map((notification) => (
                <NotificationItem key={notification.id} notification={notification} onOpen={open} />
              ))}
            </ul>
            {cursor !== null && (
              <div className="notif-more">
                <button type="button" className="btn btn-secondary btn-sm" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? "Cargando..." : "Ver más"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
