import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Reservation, ReservationStatus } from "../types";
import { CheckIcon } from "./icons";

const STATUS_LABEL: Record<ReservationStatus, string> = {
  pending: "Pendiente",
  confirmed: "Confirmada",
  cancelled: "Cancelada",
  fulfilled: "Retirada",
};

function StatusBadge({ status }: { status: ReservationStatus }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function LibrarianPanel() {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [librarian, setLibrarian] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReservations(await api.listReservations());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar las reservas");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const confirm = async (id: number) => {
    if (!librarian.trim()) {
      setError("Ingresá tu nombre para confirmar reservas.");
      return;
    }
    setError(null);
    try {
      await api.confirmReservation(id, librarian.trim());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al confirmar la reserva");
    }
  };

  return (
    <div className="librarian-panel">
      <h2>Panel bibliotecario</h2>
      <p className="hint">
        Demo sin autenticación: en la arquitectura objetivo este panel requiere login (Cognito) antes de
        exponerse.
      </p>
      <label className="librarian-name">
        Bibliotecario/a
        <input
          value={librarian}
          onChange={(event) => setLibrarian(event.target.value)}
          placeholder="Tu nombre"
        />
      </label>

      {error && <p className="error">{error}</p>}

      {loading ? (
        <p className="muted">Cargando reservas...</p>
      ) : reservations.length === 0 ? (
        <p className="empty">No hay reservas todavía.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ejemplar</th>
                <th>Solicitante</th>
                <th>Estado</th>
                <th>Confirmado por</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {reservations.map((reservation) => (
                <tr key={reservation.id}>
                  <td>
                    <span className="badge">#{reservation.copy_id}</span>
                  </td>
                  <td>
                    {reservation.patron_name} <span className="muted">({reservation.patron_email})</span>
                  </td>
                  <td>
                    <StatusBadge status={reservation.status} />
                  </td>
                  <td>{reservation.confirmed_by ?? <span className="muted">—</span>}</td>
                  <td>
                    {reservation.status === "pending" && (
                      <button className="confirm-button" onClick={() => confirm(reservation.id)}>
                        <CheckIcon />
                        Confirmar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
