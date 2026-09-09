import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { ToastViewport } from "../components/Toast";
import { describeError } from "../lib/errors";

export type ToastVariant = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  variant: ToastVariant;
  message: string;
  /** Milisegundos hasta que se cierra solo. `0` = se queda hasta que lo cierren. */
  duration: number;
}

export interface ToastInput {
  message: string;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastApi {
  /** Caso general: variante y duración explícitas. */
  show: (input: ToastInput) => string;
  /** Una acción salió bien. */
  success: (message: string, options?: { duration?: number }) => string;
  /**
   * Una acción falló. Acepta el error crudo de `api.ts` y lo traduce con
   * `describeError`, así ninguna pantalla tiene que repetir esa conversión.
   * `overrides` redacta el mensaje por status, igual que en `ErrorBanner`.
   */
  error: (error: unknown, overrides?: Partial<Record<number, string>>) => string;
  warning: (message: string, options?: { duration?: number }) => string;
  info: (message: string, options?: { duration?: number }) => string;
  dismiss: (id: string) => void;
}

/** Cuánto dura un toast por defecto. Cada llamada puede pisarlo con `duration`. */
export const DEFAULT_TOAST_DURATION = 5000;

/** Tope de toasts a la vez: al pasarse, se descarta el más viejo. */
const MAX_VISIBLE = 4;

const ToastContext = createContext<ToastApi | null>(null);

/**
 * Estado de los toasts de la app.
 *
 * A propósito no dibuja nada: la presentación entera vive en `components/Toast.tsx` y
 * en el bloque `Toasts` de `index.css`. Para rediseñarlos alcanza con tocar esos dos,
 * sin pasar por acá ni por las pantallas que los disparan.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback(({ message, variant = "info", duration }: ToastInput) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts((current) => {
      const next = [...current, { id, variant, message, duration: duration ?? DEFAULT_TOAST_DURATION }];
      // Una ráfaga de acciones no puede tapar media pantalla: se van los más viejos.
      return next.slice(-MAX_VISIBLE);
    });
    return id;
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      show,
      dismiss,
      success: (message, options) =>
        show({ message, variant: "success", duration: options?.duration }),
      warning: (message, options) =>
        show({ message, variant: "warning", duration: options?.duration }),
      info: (message, options) => show({ message, variant: "info", duration: options?.duration }),
      error: (error, overrides) =>
        show({
          message: typeof error === "string" ? error : describeError(error, overrides),
          variant: "error",
        }),
    }),
    [show, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (context === null) {
    throw new Error("useToast tiene que usarse dentro de un <ToastProvider>");
  }
  return context;
}
