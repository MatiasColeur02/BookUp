import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { startLogin, startSignup } from "../lib/auth";

interface LocationState {
  from?: { pathname: string; search?: string };
}

interface Props {
  page: "login" | "signup";
}

/**
 * `/login` y `/registro` con `VITE_AUTH_MODE=cognito`: no hay formulario propio, se sale a la
 * Hosted UI. Las rutas siguen existiendo para que `RequireRole` (y el «Reservar» del
 * catálogo) manden acá con el `from` de siempre, y un deep link a `/panel` sin sesión vuelva
 * a `/panel` después del login.
 */
export function HostedUiRedirect({ page }: Props) {
  const { user, loading } = useSession();
  const location = useLocation();
  // StrictMode corre el efecto dos veces en desarrollo: dos `state` distintos y el primero
  // perdido. Con esto sale una sola navegación.
  const started = useRef(false);
  const [error, setError] = useState<string | null>(null);

  const origin = (location.state as LocationState | null)?.from;
  const from = origin ? `${origin.pathname}${origin.search ?? ""}` : "/";

  useEffect(() => {
    if (loading || user || started.current) return;
    started.current = true;
    try {
      (page === "signup" ? startSignup : startLogin)(from);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [loading, user, page, from]);

  // Con sesión abierta no hay nada que hacer en la Hosted UI.
  if (user) return <Navigate to={from} replace />;

  return (
    <div className="auth-view">
      <div className="card form">
        <h2>{page === "signup" ? "Crear cuenta" : "Ingresar"}</h2>
        {error ? (
          <p className="callout callout-danger" role="alert">
            El ingreso no está configurado: {error}
          </p>
        ) : (
          <p className="muted">Te llevamos a la página de ingreso...</p>
        )}
      </div>
    </div>
  );
}
