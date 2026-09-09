import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../../api";
import { useToast } from "../../context/ToastContext";
import { useSession } from "../../context/SessionContext";
import { describeError } from "../../lib/errors";
import { isValidIsbn13 } from "../../lib/isbn";
import { ErrorBanner } from "../ErrorBanner";
import type {
  Book,
  Library,
  ManualPhysicalBookStatus,
  PhysicalBook,
  PhysicalBookStatus,
} from "../../types";

const ANY = "all";

const STATUS_LABELS: Record<PhysicalBookStatus, string> = {
  available: "Disponible",
  reserved: "Reservado",
  loaned: "Prestado",
  lost: "Perdido",
};

const STATUS_CLASSES: Record<PhysicalBookStatus, string> = {
  available: "status-confirmed",
  reserved: "status-pending",
  loaned: "status-fulfilled",
  lost: "status-cancelled",
};

export function PhysicalBooksAdmin() {
  const toast = useToast();
  const { isSysadmin, myLibraryId } = useSession();

  const [copies, setCopies] = useState<PhysicalBook[]>([]);
  const [books, setBooks] = useState<Book[]>([]);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [isbnFilter, setIsbnFilter] = useState("");
  const [libraryFilter, setLibraryFilter] = useState<string>(ANY);
  const [statusFilter, setStatusFilter] = useState<string>(ANY);

  const [newIsbn, setNewIsbn] = useState("");
  // Un `librarian` solo puede dar de alta en su propia sede.
  const [newLibraryId, setNewLibraryId] = useState<string>("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    Promise.all([api.books.listAll(), api.libraries.list()])
      .then(([nextBooks, nextLibraries]) => {
        setBooks(nextBooks);
        setLibraries(nextLibraries);
      })
      .catch((err) => setError(describeError(err)));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCopies(
        await api.physicalBooks.list({
          isbn: isbnFilter.trim() === "" ? undefined : isbnFilter.trim(),
          library_id: isSysadmin
            ? libraryFilter === ANY
              ? undefined
              : Number(libraryFilter)
            : myLibraryId ?? undefined,
          status: statusFilter === ANY ? undefined : (statusFilter as PhysicalBookStatus),
        })
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [isbnFilter, libraryFilter, statusFilter, isSysadmin, myLibraryId]);

  useEffect(() => {
    load();
  }, [load]);

  const titleFor = (isbn: string) => books.find((book) => book.isbn === isbn)?.title ?? isbn;
  const libraryFor = (id: number) => libraries.find((library) => library.id === id)?.name ?? `#${id}`;

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    const libraryId = isSysadmin ? Number(newLibraryId) : myLibraryId;

    if (!isValidIsbn13(newIsbn)) {
      setError("El ISBN tiene que ser un ISBN-13 válido de un libro ya cargado en el catálogo.");
      return;
    }
    if (!libraryId) {
      setError("Elegí una sede para el ejemplar.");
      return;
    }

    setCreating(true);
    setError(null);
    try {
      const created = await api.physicalBooks.create({ isbn: newIsbn, library_id: libraryId });
      toast.success(`Ejemplar #${created.id} dado de alta.`);
      setNewIsbn("");
      await load();
    } catch (err) {
      setError(
        describeError(err, {
          404: "No existe el libro o la sede: cargá el libro en el catálogo antes de darle ejemplares.",
        })
      );
    } finally {
      setCreating(false);
    }
  };

  const changeStatus = async (copy: PhysicalBook, status: ManualPhysicalBookStatus) => {
    if (status === "lost" && (copy.status === "reserved" || copy.status === "loaned")) {
      const confirmed = window.confirm(
        "Este ejemplar está reservado o prestado. Marcarlo perdido cierra sola la reserva abierta. ¿Seguir?"
      );
      if (!confirmed) return;
    }

    setError(null);
    setBusyId(copy.id);
    try {
      await api.physicalBooks.updateStatus(copy.id, { status });
      toast.success(
        status === "lost"
          ? `Ejemplar #${copy.id} marcado como extraviado.`
          : `Ejemplar #${copy.id} volvió a estar disponible.`
      );
      await load();
    } catch (err) {
      toast.error(err, {
        409: "La API solo acepta pasar a «disponible» desde «perdido»: liberar un ejemplar reservado o prestado se hace cancelando o devolviendo la reserva.",
      });
    } finally {
      setBusyId(null);
    }
  };

  const handleRemove = async (copy: PhysicalBook) => {
    if (!window.confirm(`¿Dar de baja el ejemplar #${copy.id}?`)) return;
    setError(null);
    setBusyId(copy.id);
    try {
      await api.physicalBooks.remove(copy.id);
      toast.success(`Ejemplar #${copy.id} dado de baja.`);
      await load();
    } catch (err) {
      toast.error(err, {
        409: "No se puede borrar: el ejemplar tiene reservas asociadas, incluso cerradas, y el historial las referencia. Para sacarlo de circulación marcalo «perdido».",
      });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="librarian-panel">
      <h2>Ejemplares</h2>
      <p className="hint">
        El ejemplar físico es lo que se reserva. Solo se puede pasar a mano a «disponible» o
        «perdido»: «reservado» y «prestado» los maneja el flujo de reservas. Marcar «perdido» cierra
        la reserva abierta que hubiera, y volver a «disponible» solo sale de «perdido».
      </p>

      <ErrorBanner error={error} />

      <form className="extend-form" onSubmit={handleCreate}>
        <label className="inline-select">
          ISBN
          <input
            value={newIsbn}
            onChange={(event) => setNewIsbn(event.target.value)}
            inputMode="numeric"
            maxLength={13}
            required
          />
        </label>
        {isSysadmin ? (
          <label className="inline-select">
            Sede
            <select
              value={newLibraryId}
              onChange={(event) => setNewLibraryId(event.target.value)}
              required
            >
              <option value="">Elegir...</option>
              {libraries.map((library) => (
                <option key={library.id} value={library.id}>
                  {library.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className="field-hint">
            Se da de alta en tu sede: {myLibraryId ? libraryFor(myLibraryId) : "sin sede asignada"}
          </span>
        )}
        <button type="submit" className="confirm-button" disabled={creating}>
          {creating ? "Creando..." : "Alta de ejemplar"}
        </button>
      </form>

      <div className="panel-filters">
        <label className="inline-select">
          ISBN
          <input
            value={isbnFilter}
            onChange={(event) => setIsbnFilter(event.target.value)}
            placeholder="Todos"
          />
        </label>
        {isSysadmin && (
          <label className="inline-select">
            Sede
            <select value={libraryFilter} onChange={(event) => setLibraryFilter(event.target.value)}>
              <option value={ANY}>Todas</option>
              {libraries.map((library) => (
                <option key={library.id} value={library.id}>
                  {library.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="inline-select">
          Estado
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value={ANY}>Todos</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <p className="muted">Cargando ejemplares...</p>
      ) : copies.length === 0 ? (
        <p className="empty">No hay ejemplares para estos filtros.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Id</th>
                <th>Libro</th>
                <th>Sede</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {copies.map((copy) => (
                <tr key={copy.id}>
                  <td>
                    <span className="badge">#{copy.id}</span>
                  </td>
                  <td>{titleFor(copy.isbn)}</td>
                  <td>{libraryFor(copy.library_id)}</td>
                  <td>
                    <span className={`status-badge ${STATUS_CLASSES[copy.status]}`}>
                      {STATUS_LABELS[copy.status]}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      {copy.status === "lost" ? (
                        <button
                          className="row-button"
                          onClick={() => changeStatus(copy, "available")}
                          disabled={busyId === copy.id}
                        >
                          Marcar disponible
                        </button>
                      ) : (
                        <button
                          className="row-button"
                          onClick={() => changeStatus(copy, "lost")}
                          disabled={busyId === copy.id}
                        >
                          Marcar perdido
                        </button>
                      )}
                      <button
                        className="row-button danger"
                        onClick={() => handleRemove(copy)}
                        disabled={busyId === copy.id}
                      >
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
