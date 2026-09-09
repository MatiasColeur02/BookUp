import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useToast } from "../context/ToastContext";
import { ErrorBanner } from "./ErrorBanner";

interface LocationState {
  from?: { pathname: string; search?: string };
}

export function LoginForm() {
  const toast = useToast();
  const { login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // A dónde iba antes de llegar acá: `RequireRole` lo guarda, y el catálogo también
  // cuando alguien sin sesión aprieta "Reservar" (el `search` lleva el ejemplar).
  const origin = (location.state as LocationState | null)?.from;
  const from = origin ? `${origin.pathname}${origin.search ?? ""}` : "/";

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const user = await login(email, password);
      toast.success(`Hola, ${user.name}.`);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-view">
      <form className="form-card" onSubmit={handleSubmit}>
        <h2>Ingresar</h2>
        {/* La API responde 401 tanto si el email no existe como si la password es
            incorrecta, a propósito: no filtrar cuál de las dos fue. */}
        <ErrorBanner error={error} overrides={{ 401: "Email o contraseña incorrectos." }} />
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label>
          Contraseña
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <div className="actions">
          <button type="submit" disabled={submitting}>
            {submitting ? "Ingresando..." : "Ingresar"}
          </button>
        </div>
        <p className="hint">
          ¿No tenés cuenta? <Link to="/registro" state={location.state}>Creá una</Link>.
        </p>
      </form>
    </div>
  );
}
