import { useState, type FormEvent } from "react";
import type { Reservation } from "../types";
import { isOpen } from "../lib/reservations";
import { CheckIcon } from "./icons";
import { Modal } from "./Modal";
import { ReservationStatusBadge } from "./ReservationStatusBadge";

/** `YYYY-MM-DD` en hora local para el `<input type="date">`. */
function toDateInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

interface Props {
  reservation: Reservation;
  bookTitle: string;
  libraryName: string | null;
  /** Solo lo sabe un `sysadmin`: la API no expone los usuarios al personal de sede. */
  userName: string | null;
  submitting: boolean;
  onPickup: () => void;
  onReturn: () => void;
  onCancelReservation: () => void;
  onExtend: (date: string) => void;
  onClose: () => void;
}

export function ReservationManageModal({
  reservation,
  bookTitle,
  libraryName,
  userName,
  submitting,
  onPickup,
  onReturn,
  onCancelReservation,
  onExtend,
  onClose,
}: Props) {
  const [extending, setExtending] = useState(false);
  const open = isOpen(reservation);

  return (
    <Modal title={`Gestionar la reserva de «${bookTitle}»`} onClose={onClose}>
      <div className="card stack manage-reservation">
        <h3>Gestionar reserva</h3>

        <dl className="detail-grid">
          <div>
            <dt>Libro</dt>
            <dd>{bookTitle}</dd>
          </div>
          {libraryName && (
            <div>
              <dt>Sede</dt>
              <dd>{libraryName}</dd>
            </div>
          )}
          {userName && (
            <div>
              <dt>Usuario</dt>
              <dd>{userName}</dd>
            </div>
          )}
          <div>
            <dt>Reservada</dt>
            <dd>{new Date(reservation.reserved_at).toLocaleDateString()}</dd>
          </div>
          <div>
            <dt>Vence</dt>
            <dd>{new Date(reservation.expires_at).toLocaleDateString()}</dd>
          </div>
          <div>
            <dt>Estado</dt>
            <dd>
              <ReservationStatusBadge reservation={reservation} />
            </dd>
          </div>
        </dl>

        {/* Solo las acciones que la API va a aceptar en este estado: el resto daría 409.
            Retirar, extender y cancelar valen antes del retiro; después, solo devolver. */}
        {!open ? (
          <p className="muted">
            La reserva ya está cerrada: no quedan acciones disponibles sobre ella.
          </p>
        ) : reservation.picked_up ? (
          <div className="manage-actions">
            <button className="btn btn-success btn-sm" onClick={onReturn} disabled={submitting}>
              <CheckIcon />
              Registrar devolución
            </button>
          </div>
        ) : extending ? (
          <ExtendForm
            currentExpiresAt={reservation.expires_at}
            submitting={submitting}
            onCancel={() => setExtending(false)}
            onSubmit={onExtend}
          />
        ) : (
          <div className="manage-actions">
            <button className="btn btn-success btn-sm" onClick={onPickup} disabled={submitting}>
              <CheckIcon />
              Marcar retirada
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => setExtending(true)} disabled={submitting}>
              Extender vencimiento
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={onCancelReservation}
              disabled={submitting}
            >
              Cancelar reserva
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

interface ExtendFormProps {
  currentExpiresAt: string;
  submitting: boolean;
  onSubmit: (date: string) => void;
  onCancel: () => void;
}

function ExtendForm({ currentExpiresAt, submitting, onSubmit, onCancel }: ExtendFormProps) {
  const [date, setDate] = useState(() => toDateInput(new Date(currentExpiresAt)));
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    // La API exige un vencimiento futuro (422): chequearlo acá ahorra el ida y vuelta.
    if (new Date(`${date}T23:59:59`) <= new Date()) {
      setError("El nuevo vencimiento tiene que ser futuro.");
      return;
    }
    setError(null);
    onSubmit(date);
  };

  return (
    <form className="extend-form" onSubmit={handleSubmit}>
      <label className="field field-inline">
        Nuevo vencimiento
        <input
          type="date"
          value={date}
          min={toDateInput(new Date(Date.now() + 24 * 60 * 60 * 1000))}
          onChange={(event) => setDate(event.target.value)}
          required
        />
      </label>
      <button type="submit" className="btn btn-success btn-sm" disabled={submitting}>
        {submitting ? "Guardando..." : "Guardar"}
      </button>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel} disabled={submitting}>
        Volver
      </button>
      {error && <span className="callout callout-danger">{error}</span>}
    </form>
  );
}
