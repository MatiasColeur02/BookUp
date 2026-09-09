import { useState, type FormEvent } from "react";
import type { LibraryAvailability } from "../types";
import { CheckIcon } from "./icons";

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
  bookTitle: string;
  submitting?: boolean;
  onSubmit: (expiresAt: string) => void;
  /** Vuelve a la lista de sedes, sin cerrar la ficha del libro. */
  onBack: () => void;
  /** Cierra la ficha entera: se abandona la reserva. */
  onCancel: () => void;
}

/**
 * Elegir el vencimiento y confirmar la reserva.
 *
 * Este formulario **es** el paso de confirmación: muestra el resumen de lo que se va a
 * reservar con la misma forma que `ConfirmDialog` y confirma en verde. No se le encima
 * otro diálogo porque serían dos pasos para una sola acción, con la misma información.
 *
 * Ocupa la ficha entera en lugar de agregarse debajo de la lista de sedes: cuando un
 * libro está en muchas sedes, el botón de confirmar quedaba fuera de la pantalla.
 */
export function ReservationForm({
  option,
  bookTitle,
  submitting,
  onSubmit,
  onBack,
  onCancel,
}: Props) {
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
    <form className="form confirm confirm-positive" onSubmit={handleSubmit}>
      <button type="button" className="btn btn-ghost btn-sm back-link" onClick={onBack}>
        ‹ Volver a las sedes
      </button>

      <div className="confirm-head">
        <span className="confirm-icon" aria-hidden="true">
          <CheckIcon />
        </span>
        <h3>Confirmar reserva</h3>
      </div>

      <dl className="detail-grid confirm-details">
        <div>
          <dt>Libro</dt>
          <dd>{bookTitle}</dd>
        </div>
        <div>
          <dt>Sede</dt>
          <dd>
            {option.library.name} · {option.library.city}
          </dd>
        </div>
        <div>
          <dt>Ejemplar</dt>
          <dd>
            <span className="badge badge-neutral">#{option.physical_book_id}</span>
          </dd>
        </div>
      </dl>

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
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onCancel}
          disabled={submitting}
        >
          Cancelar
        </button>
        <button type="submit" className="btn btn-success" disabled={submitting}>
          <CheckIcon />
          {submitting ? "Reservando..." : "Confirmar reserva"}
        </button>
      </div>
    </form>
  );
}
