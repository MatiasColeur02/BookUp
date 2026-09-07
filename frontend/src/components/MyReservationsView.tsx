import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useCopyDetails } from "../hooks/useCopyDetails";
import { describeError } from "../lib/errors";
import { isOpenParam, OPEN_FILTERS, type OpenFilter } from "../lib/reservations";
import type { Reservation } from "../types";
import { canBeCancelled, ReservationStatusBadge } from "./ReservationStatusBadge";

export function MyReservationsView() {
  const [filter, setFilter] = useState<OpenFilter>("open");
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<number | null>(null);

  const lookupCopy = useCopyDetails(reservations.map((reservation) => reservation.physical_book_id));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Un `customer` recibe solo las propias: no hace falta filtrar acá.
      setReservations(await api.reservations.list({ is_open: isOpenParam(filter) }));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCancel = async (reservation: Reservation) => {
    setError(null);
    setCancellingId(reservation.id);
    try {
      await api.reservations.cancel(reservation.id);
      await load();
    } catch (err) {
      setError(
        describeError(err, {
          409: "Esta reserva ya no se puede cancelar: o está cerrada, o ya retiraste el ejemplar (en ese caso hay que devolverlo en la sede).",
        })
      );
    } finally {
      setCancellingId(null);
    }
  };

  return (
    <div className="librarian-panel">
      <h2>Mis reservas</h2>

      <div className="filters">
        {OPEN_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            className={filter === value ? "active" : ""}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      {loading ? (
        <p className="muted">Cargando reservas...</p>
      ) : reservations.length === 0 ? (
        <p className="empty">No hay reservas para mostrar.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Libro</th>
                <th>Sede</th>
                <th>Reservada</th>
                <th>Vence</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {reservations.map((reservation) => {
                const { book, library } = lookupCopy(reservation.physical_book_id);
                return (
                  <tr key={reservation.id}>
                    <td>{book?.title ?? <span className="badge">#{reservation.physical_book_id}</span>}</td>
                    <td>{library?.name ?? "—"}</td>
                    <td>{new Date(reservation.reserved_at).toLocaleDateString()}</td>
                    <td>{new Date(reservation.expires_at).toLocaleDateString()}</td>
                    <td>
                      <ReservationStatusBadge reservation={reservation} />
                    </td>
                    <td>
                      {canBeCancelled(reservation) && (
                        <button
                          className="row-button danger"
                          onClick={() => handleCancel(reservation)}
                          disabled={cancellingId === reservation.id}
                        >
                          {cancellingId === reservation.id ? "Cancelando..." : "Cancelar"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
