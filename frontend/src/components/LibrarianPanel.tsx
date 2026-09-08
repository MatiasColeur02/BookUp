import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import { useCopyDetails } from "../hooks/useCopyDetails";
import { describeError } from "../lib/errors";
import { isOpen, isOpenParam, OPEN_FILTERS, type OpenFilter } from "../lib/reservations";
import type { Library, Reservation } from "../types";
import { CheckIcon } from "./icons";
import { ReservationStatusBadge } from "./ReservationStatusBadge";
import { ErrorBanner } from "./ErrorBanner";

const ALL_LIBRARIES = "all";

/** `YYYY-MM-DD` en hora local para el `<input type="date">`. */
function toDateInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

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
  const [extendingId, setExtendingId] = useState<number | null>(null);

  const lookupCopy = useCopyDetails(reservations.map((reservation) => reservation.physical_book_id));

  const selectedLibraryId =
    libraryFilter === ALL_LIBRARIES ? undefined : Number(libraryFilter);

  useEffect(() => {
    if (!isSysadmin) return;
    api.libraries.list().then(setLibraries).catch(() => undefined);
    // Los nombres de usuario solo los puede listar un `sysadmin`. Para un `librarian`
    // la fila muestra el id: la API no le expone los datos de otros usuarios.
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

  /** Toda acción sobre una reserva: bloquea la fila, recarga y explica el 409. */
  const runAction = async (
    reservationId: number,
    action: () => Promise<unknown>,
    conflictMessage: string
  ) => {
    setError(null);
    setBusyId(reservationId);
    try {
      await action();
      setExtendingId(null);
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

  return (
    <div className="librarian-panel">
      <h2>Panel bibliotecario</h2>
      {!isSysadmin && (
        <p className="hint">
          Limitación conocida: la API no expone los datos de otros usuarios al personal de sede, así
          que la columna «Usuario» muestra el id de la persona que reservó.
        </p>
      )}

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

      <ErrorBanner error={error} />

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
                <th>Usuario</th>
                <th>Reservada</th>
                <th>Vence</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {reservations.map((reservation) => {
                const { book, library } = lookupCopy(reservation.physical_book_id);
                const open = isOpen(reservation);
                const busy = busyId === reservation.id;
                const columns = showLibraryColumn ? 7 : 6;

                return (
                  <Fragment key={reservation.id}>
                    <tr>
                      <td>
                        {book?.title ?? <span className="badge">#{reservation.physical_book_id}</span>}
                      </td>
                      {showLibraryColumn && <td>{library?.name ?? "—"}</td>}
                      <td>{userNames[reservation.user_id] ?? `#${reservation.user_id}`}</td>
                      <td>{new Date(reservation.reserved_at).toLocaleDateString()}</td>
                      <td>{new Date(reservation.expires_at).toLocaleDateString()}</td>
                      <td>
                        <ReservationStatusBadge reservation={reservation} />
                      </td>
                      <td>
                        {/* Solo las acciones que la API va a aceptar en este estado: el
                            resto daría 409. */}
                        <div className="row-actions">
                          {open && !reservation.picked_up && (
                            <>
                              <button
                                className="confirm-button"
                                onClick={() => markPickedUp(reservation)}
                                disabled={busy}
                              >
                                <CheckIcon />
                                Marcar retirada
                              </button>
                              <button
                                className="row-button"
                                onClick={() =>
                                  setExtendingId(extendingId === reservation.id ? null : reservation.id)
                                }
                                disabled={busy}
                              >
                                Extender
                              </button>
                              <button
                                className="row-button danger"
                                onClick={() => cancel(reservation)}
                                disabled={busy}
                              >
                                Cancelar
                              </button>
                            </>
                          )}
                          {open && reservation.picked_up && (
                            <button
                              className="confirm-button"
                              onClick={() => markReturned(reservation)}
                              disabled={busy}
                            >
                              <CheckIcon />
                              Registrar devolución
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {extendingId === reservation.id && (
                      <tr>
                        <td colSpan={columns}>
                          <ExtendForm
                            currentExpiresAt={reservation.expires_at}
                            submitting={busy}
                            onCancel={() => setExtendingId(null)}
                            onSubmit={(date) => extend(reservation, date)}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
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
      <label className="inline-select">
        Nuevo vencimiento
        <input
          type="date"
          value={date}
          min={toDateInput(new Date(Date.now() + 24 * 60 * 60 * 1000))}
          onChange={(event) => setDate(event.target.value)}
          required
        />
      </label>
      <button type="submit" className="confirm-button" disabled={submitting}>
        {submitting ? "Guardando..." : "Guardar"}
      </button>
      <button type="button" className="row-button" onClick={onCancel} disabled={submitting}>
        Cancelar
      </button>
      {error && <span className="error">{error}</span>}
    </form>
  );
}
