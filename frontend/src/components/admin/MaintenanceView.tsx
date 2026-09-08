import { useState } from "react";
import { api } from "../../api";
import { ErrorBanner } from "../ErrorBanner";

export function MaintenanceView() {
  const [running, setRunning] = useState(false);
  const [expired, setExpired] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);

  const handleExpire = async () => {
    setRunning(true);
    setError(null);
    setExpired(null);
    try {
      const result = await api.reservations.expire();
      setExpired(result.expired);
    } catch (err) {
      setError(err);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="librarian-panel">
      <h2>Mantenimiento</h2>

      <ErrorBanner error={error} />

      <div className="form-card">
        <h3>Vencer reservas no retiradas</h3>
        <p className="hint">
          Cierra las reservas abiertas cuyo vencimiento ya pasó y que nadie retiró, y devuelve esos
          ejemplares a «disponible». Un préstamo vencido —ya retirado— no se toca: eso se resuelve
          con una devolución. Es idempotente: correrla dos veces no cambia nada, está pensada para un
          cron (EventBridge en la arquitectura target).
        </p>
        {expired !== null && (
          <p className="success">
            {expired === 0
              ? "No había reservas vencidas para cerrar."
              : `Se cerraron ${expired} reserva${expired === 1 ? "" : "s"} vencida${expired === 1 ? "" : "s"}.`}
          </p>
        )}
        <div className="actions">
          <button type="button" onClick={handleExpire} disabled={running}>
            {running ? "Procesando..." : "Vencer reservas"}
          </button>
        </div>
      </div>
    </section>
  );
}
