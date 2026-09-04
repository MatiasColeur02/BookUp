import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Reservation } from "../types";

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
        <p>Cargando reservas...</p>
      ) : reservations.length === 0 ? (
        <p className="empty">No hay reservas todavía.</p>
      ) : (
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
                <td>#{reservation.copy_id}</td>
                <td>
                  {reservation.patron_name} <span className="muted">({reservation.patron_email})</span>
                </td>
                <td>{reservation.status}</td>
                <td>{reservation.confirmed_by ?? "-"}</td>
                <td>
                  {reservation.status === "pending" && (
                    <button onClick={() => confirm(reservation.id)}>Confirmar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
