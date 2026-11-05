import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import { useToast } from "../context/ToastContext";
import { isCognito, signUp } from "../lib/auth";
import { LIMITS } from "../lib/limits";
import { ConfirmSignUpStep } from "./ConfirmSignUpStep";
import { ErrorBanner } from "./ErrorBanner";

interface LocationState {
  from?: { pathname: string; search?: string };
}

export function RegisterForm() {
  const toast = useToast();
  const { login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // Solo con Cognito: el alta queda pendiente hasta que se confirma el código del email.
  const [awaitingCode, setAwaitingCode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  /** El alta no devuelve token: se ingresa acá para no pedir la password dos veces. */
  const signInAndContinue = async () => {
    const outcome = await login(email, password);
    // Un lector recién registrado nunca tiene contraseña temporal; si pasara, que ingrese.
    if (outcome.kind !== "signed-in") {
      navigate("/login", { replace: true, state: location.state });
      return;
    }
    toast.success("Cuenta creada. Ya estás con la sesión iniciada.");
    // Si venía de "Reservar" sin sesión, vuelve al ejemplar que había elegido.
    const origin = (location.state as LocationState | null)?.from;
    navigate(origin ? `${origin.pathname}${origin.search ?? ""}` : "/", { replace: true });
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (isCognito) {
        // La cuenta nace en Cognito sin confirmar; el `User` (`customer`) lo crea el trigger
        // Post Confirmation cuando se confirma el código.
        await signUp(email, password, name);
        setAwaitingCode(true);
        return;
      }
      // Auto-registro público: la API fuerza `role=customer`. El personal se da de
      // alta desde `POST /users/staff` (Fase 6.2).
      await api.users.create({ email, password, name });
      await signInAndContinue();
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (awaitingCode) {
    return (
      <div className="auth-view">
        <ConfirmSignUpStep email={email} onConfirmed={signInAndContinue} />
      </div>
    );
  }

  return (
    <div className="auth-view">
      <form className="card form" onSubmit={handleSubmit}>
        <h2>Crear cuenta</h2>
        <ErrorBanner error={error} overrides={{ 409: "Ese email ya está registrado." }} />
        <label>
          Nombre
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={LIMITS.user.name}
            required
          />
        </label>
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
            autoComplete="new-password"
            minLength={LIMITS.user.passwordMin}
            maxLength={LIMITS.user.passwordMax}
            required
          />
          <span className="field-hint">Al menos 8 caracteres.</span>
        </label>
        <div className="actions">
          <button type="submit" className="btn btn-primary btn-lg" disabled={submitting}>
            {submitting ? "Creando..." : "Crear cuenta"}
          </button>
        </div>
        <p className="hint">
          ¿Ya tenés cuenta? <Link to="/login" state={location.state}>Ingresá</Link>.
        </p>
      </form>
    </div>
  );
}
