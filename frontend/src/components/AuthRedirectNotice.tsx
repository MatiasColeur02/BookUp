import { useEffect, useState } from "react";
import { useSession } from "../context/SessionContext";
import { useToast } from "../context/ToastContext";
import { describeAuthError, takeAuthRedirectResult } from "../lib/auth";

/**
 * Cuenta por toast cómo terminó la vuelta de la Hosted UI (`lib/auth.ts`): el saludo si
 * entró, o por qué no. `consumeAuthRedirect` corre antes de React y no puede mostrar nada.
 */
export function AuthRedirectNotice() {
  const toast = useToast();
  const { user, loading } = useSession();
  // Se lee una sola vez: `takeAuthRedirectResult` lo consume.
  const [result] = useState(takeAuthRedirectResult);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (shown || result.kind === "none") return;
    if (result.kind === "error") {
      setShown(true);
      if (result.error === "access_denied") toast.info(describeAuthError(result.error));
      else toast.warning(describeAuthError(result.error));
      return;
    }
    // Entró: el saludo espera a que `GET /auth/me` traiga el nombre.
    if (loading) return;
    setShown(true);
    if (user) toast.success(`Hola, ${user.name}.`);
  }, [result, shown, user, loading, toast]);

  return null;
}
