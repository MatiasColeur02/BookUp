import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import { useCopyDetails } from "../hooks/useCopyDetails";
import { describeError } from "../lib/errors";
import { isOpen, isOpenParam, OPEN_FILTERS, type OpenFilter } from "../lib/reservations";
import type { Library, Reservation } from "../types";
import { ReservationManageModal } from "./ReservationManageModal";
import { ReservationStatusBadge } from "./ReservationStatusBadge";
import { ErrorBanner } from "./ErrorBanner";

const ALL_LIBRARIES = "all";

export function LibrarianPanel() {
  const { isSysadmin, myLibraryId } = useSession();

  const [filter, setFilter] = useState<OpenFilter>("open");
  // Un `librarian` solo puede ver su sede (pedir otra da 403), así que el selector es
  // solo para `sysadmin`.
  const [libraryFilter, setLibraryFilter] = useState<string>(ALL_LIBRARIES);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [userNames, setUserNames] = useState<Record<number, string>>({});

  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [managingId, setManagingId] = useState<number | null>(null);

  const lookupCopy = useCopyDetails(reservations.map((reservation) => reservation.physical_book_id));

  const selectedLibraryId =
    libraryFilter === ALL_LIBRARIES ? undefined : Number(libraryFilter);

  useEffect(() => {
    if (!isSysadmin) return;
    api.libraries.list().then(setLibraries).catch(() => undefined);
    // Los nombres de usuario solo los puede listar un `sysadmin`: la API no le expone
    // los datos de otros usuarios al personal de sede. Sin nombres, la columna
    // «Usuario» directamente no se muestra.
    api.users
      .list()
      .then((users) => setUserNames(Object.fromEntries(users.map((u) => [u.id, u.name]))))
      .catch(() => undefined);
  }, [isSysadmin]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReservations(
        await api.reservations.list({
          is_open: isOpenParam(filter),
          // El `librarian` queda fijado a su sede; el `sysadmin` elige.
          library_id: isSysadmin ? selectedLibraryId : myLibraryId ?? undefined,
        })
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [filter, isSysadmin, selectedLibraryId, myLibraryId]);

  useEffect(() => {
    load();
  }, [load]);

  /**
   * Toda acción sobre una reserva: bloquea el diálogo, recarga y explica el 409.
   * Si sale bien cierra el modal; si falla lo deja abierto con el error a la vista.
   */
  const runAction = async (
    reservationId: number,
    action: () => Promise<unknown>,
    conflictMessage: string
  ) => {
    setError(null);
    setBusyId(reservationId);
    try {
      await action();
      setManagingId(null);
      await load();
    } catch (err) {
      setError(describeError(err, { 409: conflictMessage }));
    } finally {
      setBusyId(null);
    }
  };

  const markPickedUp = (reservation: Reservation) =>
    runAction(
      reservation.id,
      () => api.reservations.markPickedUp(reservation.id),
      "No se puede marcar el retiro: la reserva ya está cerrada o el ejemplar ya se había retirado."
    );

  const markReturned = (reservation: Reservation) =>
    runAction(
      reservation.id,
      () => api.reservations.markReturned(reservation.id),
      "No se puede registrar la devolución: la reserva ya está cerrada o el ejemplar nunca se retiró (en ese caso corresponde cancelarla)."
    );

  const cancel = (reservation: Reservation) =>
    runAction(
      reservation.id,
      () => api.reservations.cancel(reservation.id),
      "No se puede cancelar: la reserva ya está cerrada o el ejemplar ya fue retirado (en ese caso corresponde registrar la devolución)."
    );

  const extend = (reservation: Reservation, date: string) =>
    runAction(
      reservation.id,
      () => api.reservations.update(reservation.id, { expires_at: new Date(`${date}T23:59:59`).toISOString() }),
      "No se puede extender: la reserva ya está cerrada o el ejemplar ya fue retirado."
    );

  const showLibraryColumn = isSysadmin && selectedLibraryId === undefined;
  // Sin los nombres (todo rol que no sea `sysadmin`) la columna no aporta nada.
  const showUserColumn = isSysadmin;
  const managed = reservations.find((reservation) => reservation.id === managingId) ?? null;

  return (
    <div className="librarian-panel">
      <h2>Panel bibliotecario</h2>

      <div className="panel-filters">
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

        {isSysadmin && (
          <label className="inline-select">
            Sede
            <select value={libraryFilter} onChange={(event) => setLibraryFilter(event.target.value)}>
              <option value={ALL_LIBRARIES}>Todas</option>
              {libraries.map((library) => (
                <option key={library.id} value={library.id}>
                  {library.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {/* Con el modal abierto el error se muestra ahí, al lado del botón que falló. */}
      <ErrorBanner error={managed === null ? error : null} />

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
                {showLibraryColumn && <th>Sede</th>}
                {showUserColumn && <th>Usuario</th>}
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
                    <td>
                      {book?.title ?? <span className="badge">#{reservation.physical_book_id}</span>}
                    </td>
                    {showLibraryColumn && <td>{library?.name ?? "—"}</td>}
                    {showUserColumn && <td>{userNames[reservation.user_id] ?? "—"}</td>}
                    <td>{new Date(reservation.reserved_at).toLocaleDateString()}</td>
                    <td>{new Date(reservation.expires_at).toLocaleDateString()}</td>
                    <td>
                      <ReservationStatusBadge reservation={reservation} />
                    </td>
                    <td>
                      {/* Una reserva cerrada no admite ninguna acción: sin botón. */}
                      {isOpen(reservation) && (
                        <div className="row-actions">
                          <button
                            className="row-button"
                            onClick={() => setManagingId(reservation.id)}
                          >
                            Gestionar
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {managed && (
        <ReservationManageModal
          reservation={managed}
          bookTitle={
            lookupCopy(managed.physical_book_id).book?.title ??
            `Ejemplar #${managed.physical_book_id}`
          }
          libraryName={lookupCopy(managed.physical_book_id).library?.name ?? null}
          userName={userNames[managed.user_id] ?? null}
          submitting={busyId === managed.id}
          error={error}
          onPickup={() => markPickedUp(managed)}
          onReturn={() => markReturned(managed)}
          onCancelReservation={() => cancel(managed)}
          onExtend={(date) => extend(managed, date)}
          onClose={() => {
            setManagingId(null);
            setError(null);
          }}
        />
      )}
    </div>
  );
}
