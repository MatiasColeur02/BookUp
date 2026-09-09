import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { ConfirmDialog, type ConfirmOptions } from "../components/ConfirmDialog";

type Confirm = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<Confirm | null>(null);

/**
 * Confirmaciones de la app.
 *
 * La API es a propósito la de `window.confirm` —una promesa que devuelve `true` o
 * `false`— para que en cada pantalla la guarda siga siendo una línea:
 *
 * ```ts
 * if (!(await confirm({ tone: "danger", title: "¿Eliminar…?" }))) return;
 * ```
 *
 * El estado vive acá y el aspecto en `components/ConfirmDialog.tsx`, igual que con los
 * toasts: rediseñar el diálogo no toca ninguna pantalla.
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<ConfirmOptions | null>(null);
  // El `resolve` de la promesa en curso: lo llama el botón que se apriete.
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback<Confirm>((options) => {
    return new Promise<boolean>((resolve) => {
      // Si ya había un diálogo abierto (no debería), se lo cierra como cancelado para
      // no dejar una promesa colgada para siempre.
      resolveRef.current?.(false);
      resolveRef.current = resolve;
      setPending(options);
    });
  }, []);

  const settle = (value: boolean) => {
    resolveRef.current?.(value);
    resolveRef.current = null;
    setPending(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <ConfirmDialog {...pending} onConfirm={() => settle(true)} onCancel={() => settle(false)} />
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): Confirm {
  const context = useContext(ConfirmContext);
  if (context === null) {
    throw new Error("useConfirm tiene que usarse dentro de un <ConfirmProvider>");
  }
  return context;
}
