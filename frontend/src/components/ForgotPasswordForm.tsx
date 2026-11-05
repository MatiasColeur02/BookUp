import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useToast } from "../context/ToastContext";
import { confirmForgotPassword, forgotPassword } from "../lib/auth";
import { LIMITS } from "../lib/limits";
import { ErrorBanner } from "./ErrorBanner";

interface LocationState {
  from?: { pathname: string; search?: string };
}

/**
 * «Olvidé mi contraseña», solo con Cognito: el User Pool manda un código al email y con él se
 * elige la nueva. Al terminar se ingresa con esa contraseña. Con `prevent_user_existence_errors`
 * Cognito contesta igual exista o no la cuenta, así que esta pantalla no revela qué emails
 * están registrados.
 */
export function ForgotPasswordForm() {
  const toast = useToast();
  const { login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const origin = (location.state as LocationState | null)?.from;
  const from = origin ? `${origin.pathname}${origin.search ?? ""}` : "/";

  const handleRequest = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await forgotPassword(email);
      setCodeSent(true);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirm = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await confirmForgotPassword(email, code.trim(), password);
      const outcome = await login(email, password);
      if (outcome.kind === "signed-in") {
        toast.success("Contraseña actualizada. Ya estás con la sesión iniciada.");
        navigate(from, { replace: true });
      } else {
        navigate("/login", { replace: true, state: location.state });
      }
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (codeSent) {
    return (
      <div className="auth-view">
        <form className="card form" onSubmit={handleConfirm}>
          <h2>Elegí una contraseña nueva</h2>
          <p className="hint">
            Si {email} tiene una cuenta, le mandamos un código. Puede tardar un par de minutos.
          </p>
          <ErrorBanner error={error} />
          <label>
            Código
            <input
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={10}
              required
            />
          </label>
          <label>
            Contraseña nueva
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={LIMITS.user.passwordMin}
              maxLength={LIMITS.user.passwordMax}
              required
            />
            <span className="field-hint">Al menos 8 caracteres.</span>
          </label>
          <div className="actions">
            <button type="button" className="btn btn-ghost" onClick={() => setCodeSent(false)}>
              Volver
            </button>
            <button type="submit" className="btn btn-primary btn-lg" disabled={submitting}>
              {submitting ? "Guardando..." : "Guardar e ingresar"}
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="auth-view">
      <form className="card form" onSubmit={handleRequest}>
        <h2>Recuperar contraseña</h2>
        <p className="hint">Te mandamos un código al email para elegir una contraseña nueva.</p>
        <ErrorBanner error={error} />
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            maxLength={LIMITS.user.email}
            required
          />
        </label>
        <div className="actions">
          <button type="submit" className="btn btn-primary btn-lg" disabled={submitting}>
            {submitting ? "Enviando..." : "Enviar código"}
          </button>
        </div>
        <p className="hint">
          ¿Te acordaste? <Link to="/login" state={location.state}>Ingresá</Link>.
        </p>
      </form>
    </div>
  );
}
