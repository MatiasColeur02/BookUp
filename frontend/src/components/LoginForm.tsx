import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useToast } from "../context/ToastContext";
import {
  CognitoError,
  isCognito,
  resendConfirmationCode,
  type NewPasswordChallenge,
} from "../lib/auth";
import { LIMITS } from "../lib/limits";
import type { User } from "../types";
import { ConfirmSignUpStep } from "./ConfirmSignUpStep";
import { ErrorBanner } from "./ErrorBanner";

interface LocationState {
  from?: { pathname: string; search?: string };
}

/**
 * Los pasos del ingreso. `local` usa solo `credentials`; los otros dos son de Cognito:
 * `new-password` cuando la cuenta tiene contraseña temporal (personal dado de alta por un
 * sysadmin) y `confirm` cuando se registró pero nunca confirmó el email.
 */
type Step =
  | { kind: "credentials" }
  | { kind: "new-password"; challenge: NewPasswordChallenge }
  | { kind: "confirm" };

export function LoginForm() {
  const toast = useToast();
  const { login, completeNewPassword } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [step, setStep] = useState<Step>({ kind: "credentials" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // A dónde iba antes de llegar acá: `RequireRole` lo guarda, y el catálogo también
  // cuando alguien sin sesión aprieta "Reservar" (el `search` lleva el ejemplar).
  const origin = (location.state as LocationState | null)?.from;
  const from = origin ? `${origin.pathname}${origin.search ?? ""}` : "/";

  const welcome = (user: User) => {
    toast.success(`Hola, ${user.name}.`);
    navigate(from, { replace: true });
  };

  const signIn = async () => {
    const outcome = await login(email, password);
    if (outcome.kind === "signed-in") welcome(outcome.user);
    else setStep({ kind: "new-password", challenge: outcome.challenge });
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signIn();
    } catch (err) {
      if (err instanceof CognitoError && err.code === "UserNotConfirmedException") {
        // Se registró y no llegó a confirmar: un código nuevo y el paso de confirmación, con
        // la contraseña todavía en memoria para entrar apenas confirme.
        try {
          await resendConfirmationCode(email);
          setStep({ kind: "confirm" });
        } catch (resendError) {
          setError(resendError);
        }
      } else {
        setError(err);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleNewPassword = async (event: FormEvent) => {
    event.preventDefault();
    if (step.kind !== "new-password") return;
    setSubmitting(true);
    setError(null);
    try {
      welcome(await completeNewPassword(step.challenge, newPassword));
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (step.kind === "confirm") {
    return (
      <div className="auth-view">
        <ConfirmSignUpStep email={email} onConfirmed={signIn} />
      </div>
    );
  }

  if (step.kind === "new-password") {
    return (
      <div className="auth-view">
        <form className="card form" onSubmit={handleNewPassword}>
          <h2>Elegí tu contraseña</h2>
          <p className="hint">
            Tu cuenta tiene una contraseña temporal. Elegí la que vas a usar de ahora en más.
          </p>
          <ErrorBanner error={error} />
          <label>
            Contraseña nueva
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
              minLength={LIMITS.user.passwordMin}
              maxLength={LIMITS.user.passwordMax}
              required
            />
            <span className="field-hint">Al menos 8 caracteres.</span>
          </label>
          <div className="actions">
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
      <form className="card form" onSubmit={handleSubmit}>
        <h2>Ingresar</h2>
        {/* La API (y Cognito, con `prevent_user_existence_errors`) responde lo mismo si el
            email no existe que si la password es incorrecta, a propósito: no filtrar cuál
            de las dos fue. */}
        <ErrorBanner error={error} overrides={{ 401: "Email o contraseña incorrectos." }} />
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
        <label>
          Contraseña
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            maxLength={LIMITS.user.passwordMax}
            required
          />
        </label>
        <div className="actions">
          <button type="submit" className="btn btn-primary btn-lg" disabled={submitting}>
            {submitting ? "Ingresando..." : "Ingresar"}
          </button>
        </div>
        <p className="hint">
          ¿No tenés cuenta? <Link to="/registro" state={location.state}>Creá una</Link>.
          {isCognito && (
            <>
              {" "}
              <Link to="/recuperar" state={location.state}>
                ¿Olvidaste tu contraseña?
              </Link>
            </>
          )}
        </p>
      </form>
    </div>
  );
}
