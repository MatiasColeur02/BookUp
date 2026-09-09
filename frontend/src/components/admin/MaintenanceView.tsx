import { useState } from "react";
import { api } from "../../api";
import { useToast } from "../../context/ToastContext";

export function MaintenanceView() {
  const toast = useToast();
  const [running, setRunning] = useState(false);

  const handleExpire = async () => {
    setRunning(true);
    try {
      const { expired } = await api.reservations.expire();
      // Cerrar cero reservas es un resultado válido, no un error: la tarea es
      // idempotente y correrla de más no cambia nada.
      toast.success(
        expired === 0
          ? "No había reservas vencidas para cerrar."
          : `Se cerraron ${expired} reserva${expired === 1 ? "" : "s"} vencida${expired === 1 ? "" : "s"}.`
      );
    } catch (err) {
      toast.error(err);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="librarian-panel">
      <h2>Mantenimiento</h2>

      <div className="form-card">
        <h3>Vencer reservas no retiradas</h3>
        <p className="hint">
          Cierra las reservas abiertas cuyo vencimiento ya pasó y que nadie retiró, y devuelve esos
          ejemplares a «disponible». Un préstamo vencido —ya retirado— no se toca: eso se resuelve
          con una devolución. Es idempotente: correrla dos veces no cambia nada, está pensada para un
          cron (EventBridge en la arquitectura target).
        </p>
        <div className="actions">
          <button type="button" onClick={handleExpire} disabled={running}>
            {running ? "Procesando..." : "Vencer reservas"}
          </button>
        </div>
      </div>
    </section>
  );
}
