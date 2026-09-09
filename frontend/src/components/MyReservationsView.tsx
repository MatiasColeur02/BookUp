import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useToast } from "../context/ToastContext";
import { useCopyDetails } from "../hooks/useCopyDetails";
import { describeError } from "../lib/errors";
import { isOpenParam, isOverdue, OPEN_FILTERS, type OpenFilter } from "../lib/reservations";
import type { Reservation } from "../types";
import { canBeCancelled, ReservationStatusBadge } from "./ReservationStatusBadge";
import { ErrorBanner } from "./ErrorBanner";
import { TableSkeleton } from "./Skeleton";

export function MyReservationsView() {
  const toast = useToast();
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
      // `mine` es imprescindible: sin él, a un `librarian` la API le devuelve las
      // reservas de su sede en vez de las suyas, y a un `sysadmin` todas.
      setReservations(await api.reservations.list({ is_open: isOpenParam(filter), mine: true }));
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
      toast.success("Reserva cancelada.");
      await load();
    } catch (err) {
      toast.error(err, {
        409: "Esta reserva ya no se puede cancelar: o está cerrada, o ya retiraste el ejemplar (en ese caso hay que devolverlo en la sede).",
      });
    } finally {
      setCancellingId(null);
    }
  };

  return (
    <div className="stack">
      <h2>Mis reservas</h2>

      <div className="panel-toolbar">
        <div className="segmented segmented-sm">
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
      </div>

      <ErrorBanner error={error} />

      {loading ? (
        <TableSkeleton />
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
                    <td>{book?.title ?? <span className="badge badge-neutral">#{reservation.physical_book_id}</span>}</td>
                    <td>{library?.name ?? "—"}</td>
                    <td>{new Date(reservation.reserved_at).toLocaleDateString()}</td>
                    <td className={isOverdue(reservation) ? "overdue" : undefined}>
                      {new Date(reservation.expires_at).toLocaleDateString()}
                    </td>
                    <td>
                      <ReservationStatusBadge reservation={reservation} />
                    </td>
                    <td>
                      {canBeCancelled(reservation) && (
                        <button
                          className="btn btn-danger btn-sm"
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
