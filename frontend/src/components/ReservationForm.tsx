import { useState, type FormEvent } from "react";
import type { LibraryAvailability } from "../types";

/** Ventana por defecto para retirar el ejemplar. */
const RESERVATION_WINDOW_DAYS = 7;

/** `YYYY-MM-DD` en hora local, que es lo que espera un `<input type="date">`. */
function toDateInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function addDays(days: number): Date {
  return new Date(Date.now() + days * 24 * 60 * 60 * 1000);
}

/** Fin del día elegido: reservar "hasta el 12" incluye todo el 12. */
function endOfDay(value: string): Date {
  return new Date(`${value}T23:59:59`);
}

interface Props {
  option: LibraryAvailability;
  submitting?: boolean;
  onSubmit: (expiresAt: string) => void;
  onCancel: () => void;
}

export function ReservationForm({ option, submitting, onSubmit, onCancel }: Props) {
  const [date, setDate] = useState(() => toDateInput(addDays(RESERVATION_WINDOW_DAYS)));
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const expiresAt = endOfDay(date);
    // La API exige un `expires_at` futuro (422). Chequearlo acá evita el ida y vuelta.
    if (Number.isNaN(expiresAt.getTime()) || expiresAt <= new Date()) {
      setError("La fecha de vencimiento tiene que ser futura.");
      return;
    }
    setError(null);
    onSubmit(expiresAt.toISOString());
  };

  return (
    <form className="card card-subtle form" onSubmit={handleSubmit}>
      <h3>Reservar en {option.library.name}</h3>
      <p className="field-hint">
        Ejemplar <span className="badge badge-neutral">#{option.physical_book_id}</span> · {option.library.city}
      </p>

      {error && <p className="callout callout-danger">{error}</p>}

      <label>
        Retirar antes del
        <input
          type="date"
          value={date}
          min={toDateInput(addDays(1))}
          onChange={(event) => setDate(event.target.value)}
          required
        />
        <span className="field-hint">
          Pasada esa fecha la reserva se da de baja y el ejemplar vuelve a estar disponible.
        </span>
      </label>

      <div className="actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Reservando..." : "Confirmar reserva"}
        </button>
      </div>
    </form>
  );
}
