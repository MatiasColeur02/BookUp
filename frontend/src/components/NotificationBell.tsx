import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useNotifications } from "../context/NotificationsContext";
import { formatBadge } from "../lib/notifications";
import { BellIcon } from "./icons";
import { NotificationPanel } from "./NotificationPanel";

/**
 * La campana del header con el número rojo (`notifications-roadmap.md` §7.3). Se cierra con
 * Escape (devolviendo el foco a la campana), con un click afuera y al navegar.
 */
export function NotificationBell() {
  const { counts, total } = useNotifications();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [bump, setBump] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const previous = useRef(total);

  // Una animación corta cuando el número sube (no cuando baja).
  useEffect(() => {
    if (total > previous.current) setBump(true);
    previous.current = total;
  }, [total]);

  useEffect(() => setOpen(false), [location.pathname, location.search]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Element;
      // El diálogo de confirmación vive en un portal: clickearlo no es «afuera».
      if (root.current?.contains(target) || target.closest?.(".modal-over")) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // Un diálogo de confirmación abierto encima se cierra primero.
      if (document.querySelector(".modal-over")) return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const badge = formatBadge(total);
  const label = total > 0 ? `Notificaciones, ${total} sin leer` : "Notificaciones";

  return (
    <div className="bell-wrap" ref={root}>
      <button
        ref={button}
        type="button"
        className="btn btn-ghost btn-icon bell"
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((value) => !value)}
      >
        <BellIcon />
        {badge && (
          <span
            className={`bell-badge${bump ? " is-bumping" : ""}`}
            aria-hidden="true"
            onAnimationEnd={() => setBump(false)}
          >
            {badge}
          </span>
        )}
      </button>
      {open && (
        <NotificationPanel hasLibraryInbox={counts?.library != null} onClose={() => setOpen(false)} />
      )}
    </div>
  );
}
