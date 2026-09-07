import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Reservation } from "../types";
import { CheckIcon } from "./icons";

function StatusBadge({ pickedUp }: { pickedUp: boolean }) {
  return (
    <span className={`status-badge ${pickedUp ? "status-fulfilled" : "status-pending"}`}>
      {pickedUp ? "Retirada" : "Pendiente"}
    </span>
  );
}

export function LibrarianPanel() {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReservations(await api.reservations.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar las reservas");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const markPickedUp = async (id: number) => {
    setError(null);
    try {
      await api.reservations.markPickedUp(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al marcar el retiro");
    }
  };

  return (
    <div className="librarian-panel">
      <h2>Panel bibliotecario</h2>
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
                <th>Usuario</th>
                <th>Reservada</th>
                <th>Vence</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {reservations.map((reservation) => (
                <tr key={reservation.id}>
                  <td>
                    <span className="badge">#{reservation.physical_book_id}</span>
                  </td>
                  <td>#{reservation.user_id}</td>
                  <td>{new Date(reservation.reserved_at).toLocaleDateString()}</td>
                  <td>{new Date(reservation.expires_at).toLocaleDateString()}</td>
                  <td>
                    <StatusBadge pickedUp={reservation.picked_up} />
                  </td>
                  <td>
                    {!reservation.picked_up && (
                      <button className="confirm-button" onClick={() => markPickedUp(reservation.id)}>
                        <CheckIcon />
                        Marcar retirada
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
