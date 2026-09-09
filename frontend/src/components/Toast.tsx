import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Toast, ToastVariant } from "../context/ToastContext";
import { CheckIcon } from "./icons";

/**
 * Presentación de los toasts. Es la única capa que sabe cómo se ven: el estado vive en
 * `context/ToastContext.tsx` y las pantallas solo llaman `useToast()`. Para rediseñarlos
 * alcanza con este archivo y el bloque `Toasts` de `index.css`.
 */

const ICONS: Record<ToastVariant, string> = {
  success: "",
  error: "!",
  warning: "!",
  info: "i",
};

interface ViewportProps {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

export function ToastViewport({ toasts, onDismiss }: ViewportProps) {
  // Fuera del árbol de la app: así ningún `overflow` los recorta y quedan por encima
  // del modal sin pelear con el `z-index` de la pantalla de abajo.
  return createPortal(
    <div className="toast-viewport" role="region" aria-label="Notificaciones">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>,
    document.body
  );
}

interface ItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

function ToastItem({ toast, onDismiss }: ItemProps) {
  // El timer se pausa mientras el mouse está encima: un mensaje largo no se escapa
  // mientras lo estás leyendo.
  const [paused, setPaused] = useState(false);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  useEffect(() => {
    if (toast.duration === 0 || paused) return;
    const timer = window.setTimeout(() => onDismissRef.current(toast.id), toast.duration);
    return () => window.clearTimeout(timer);
  }, [toast.id, toast.duration, paused]);

  return (
    <div
      className={`toast toast-${toast.variant}`}
      // Un error interrumpe al lector de pantalla; una confirmación espera su turno.
      role={toast.variant === "error" ? "alert" : "status"}
      aria-live={toast.variant === "error" ? "assertive" : "polite"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <span className="toast-icon" aria-hidden="true">
        {toast.variant === "success" ? <CheckIcon /> : ICONS[toast.variant]}
      </span>
      <p className="toast-message">{toast.message}</p>
      <button
        type="button"
        className="btn btn-ghost btn-icon toast-close"
        onClick={() => onDismiss(toast.id)}
        aria-label="Cerrar notificación"
      >
        ×
      </button>
    </div>
  );
}
