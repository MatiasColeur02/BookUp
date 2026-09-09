import { useState } from "react";
import { api } from "../../api";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";

export function MaintenanceView() {
  const confirm = useConfirm();
  const toast = useToast();
  const [running, setRunning] = useState(false);

  const handleExpire = async () => {
    const confirmed = await confirm({
      tone: "danger",
      title: "Vencer reservas no retiradas",
      message:
        "Cierra todas las reservas abiertas que ya vencieron y nadie retiró, en todas las sedes, y devuelve esos ejemplares a «disponible». Es idempotente, pero las reservas cerradas no se reabren.",
      confirmLabel: "Vencer reservas",
    });
    if (!confirmed) return;

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
    <section className="stack">
      <h2>Mantenimiento</h2>

      <div className="card form">
        <h3>Vencer reservas no retiradas</h3>
        <p className="hint">
          Cierra las reservas abiertas cuyo vencimiento ya pasó y que nadie retiró, y devuelve esos
          ejemplares a «disponible». Un préstamo vencido —ya retirado— no se toca: eso se resuelve
          con una devolución. Es idempotente: correrla dos veces no cambia nada, está pensada para un
          cron (EventBridge en la arquitectura target).
        </p>
        <div className="actions">
          <button type="button" className="btn btn-primary" onClick={handleExpire} disabled={running}>
            {running ? "Procesando..." : "Vencer reservas"}
          </button>
        </div>
      </div>
    </section>
  );
}
