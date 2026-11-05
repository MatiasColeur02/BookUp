import { useState, type FormEvent } from "react";
import { useToast } from "../context/ToastContext";
import { confirmSignUp, resendConfirmationCode } from "../lib/auth";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  email: string;
  /** Después de confirmar: el formulario que lo usa ingresa con la contraseña que ya tiene. */
  onConfirmed: () => Promise<void>;
}

/**
 * Segundo paso del registro con Cognito: el código que llegó al email. Confirmarlo es lo que
 * dispara el trigger *Post Confirmation*, que crea el `User` (`customer`) en DynamoDB; recién
 * entonces `GET /auth/me` lo encuentra.
 */
export function ConfirmSignUpStep({ email, onConfirmed }: Props) {
  const toast = useToast();
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await confirmSignUp(email, code.trim());
      await onConfirmed();
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setError(null);
    try {
      await resendConfirmationCode(email);
      toast.info(`Te mandamos un código nuevo a ${email}.`);
    } catch (err) {
      setError(err);
    } finally {
      setResending(false);
    }
  };

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <h2>Confirmá tu email</h2>
      <p className="hint">
        Te mandamos un código a {email}. Puede tardar un par de minutos.
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
      <div className="actions">
        <button type="button" className="btn btn-ghost" onClick={handleResend} disabled={resending}>
          {resending ? "Enviando..." : "Reenviar código"}
        </button>
        <button type="submit" className="btn btn-primary btn-lg" disabled={submitting}>
          {submitting ? "Confirmando..." : "Confirmar"}
        </button>
      </div>
    </form>
  );
}
