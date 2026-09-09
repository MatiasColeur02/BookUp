import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../../api";
import { useConfirm } from "../../context/ConfirmContext";
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
import { TableSkeleton } from "../Skeleton";

const ANY = "all";

const STATUS_LABELS: Record<PhysicalBookStatus, string> = {
  available: "Disponible",
  reserved: "Reservado",
  loaned: "Prestado",
  lost: "Perdido",
};

const STATUS_CLASSES: Record<PhysicalBookStatus, string> = {
  available: "badge-success",
  reserved: "badge-warning",
  loaned: "badge-neutral",
  lost: "badge-danger",
};

export function PhysicalBooksAdmin() {
  const confirm = useConfirm();
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

  // La ficha del diálogo nombra el ejemplar por su libro y su sede; el id, que es la
  // clave interna, solo se lista para un sysadmin.
  const copyDetails = (copy: PhysicalBook) => [
    { label: "Libro", value: titleFor(copy.isbn) },
    { label: "ISBN", value: copy.isbn },
    { label: "Sede", value: libraryFor(copy.library_id) },
    ...(isSysadmin ? [{ label: "Ejemplar", value: `#${copy.id}` }] : []),
  ];

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
      toast.success(`Ejemplar de «${titleFor(created.isbn)}» dado de alta.`);
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
    if (status === "lost") {
      const open = copy.status === "reserved" || copy.status === "loaned";
      const confirmed = await confirm({
        tone: "danger",
        title: "Marcar como extraviado",
        message: open
          ? "Este ejemplar está reservado o prestado: marcarlo perdido cierra sola la reserva abierta."
          : "El ejemplar sale de circulación. Podés devolverlo a «disponible» más adelante.",
        details: copyDetails(copy),
        confirmLabel: "Marcar perdido",
      });
      if (!confirmed) return;
    }

    setError(null);
    setBusyId(copy.id);
    try {
      await api.physicalBooks.updateStatus(copy.id, { status });
      toast.success(
        status === "lost"
          ? `Un ejemplar de «${titleFor(copy.isbn)}» quedó marcado como extraviado.`
          : `Un ejemplar de «${titleFor(copy.isbn)}» volvió a estar disponible.`
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
    const confirmed = await confirm({
      tone: "danger",
      title: "Dar de baja el ejemplar",
      message:
        "Se borra de la base. Si tuvo reservas, aunque estén cerradas, la API lo va a rechazar: en ese caso marcalo «perdido».",
      details: copyDetails(copy),
      confirmLabel: "Dar de baja",
    });
    if (!confirmed) return;
    setError(null);
    setBusyId(copy.id);
    try {
      await api.physicalBooks.remove(copy.id);
      toast.success(`Se dio de baja un ejemplar de «${titleFor(copy.isbn)}».`);
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
    <section className="stack">
      <h2>Ejemplares</h2>
      <p className="hint">
        El ejemplar físico es lo que se reserva. Solo se puede pasar a mano a «disponible» o
        «perdido»: «reservado» y «prestado» los maneja el flujo de reservas. Marcar «perdido» cierra
        la reserva abierta que hubiera, y volver a «disponible» solo sale de «perdido».
      </p>

      <ErrorBanner error={error} />

      <form className="create-form" onSubmit={handleCreate}>
        <label className="field field-inline">
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
          <label className="field field-inline">
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
        <button type="submit" className="btn btn-primary" disabled={creating}>
          {creating ? "Creando..." : "Alta de ejemplar"}
        </button>
      </form>

      <div className="panel-toolbar">
        <label className="field field-inline">
          ISBN
          <input
            value={isbnFilter}
            onChange={(event) => setIsbnFilter(event.target.value)}
            placeholder="Todos"
          />
        </label>
        {isSysadmin && (
          <label className="field field-inline">
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
        <label className="field field-inline">
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
        <TableSkeleton />
      ) : copies.length === 0 ? (
        <p className="empty">No hay ejemplares para estos filtros.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {isSysadmin && <th>Id</th>}
                <th>Libro</th>
                <th>Sede</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {copies.map((copy) => (
                <tr key={copy.id}>
                  {isSysadmin && (
                    <td>
                      <span className="badge badge-neutral">#{copy.id}</span>
                    </td>
                  )}
                  <td>{titleFor(copy.isbn)}</td>
                  <td>{libraryFor(copy.library_id)}</td>
                  <td>
                    <span className={`badge ${STATUS_CLASSES[copy.status]}`}>
                      {STATUS_LABELS[copy.status]}
                    </span>
                  </td>
                  <td>
                    <div className="row-actions">
                      {copy.status === "lost" ? (
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => changeStatus(copy, "available")}
                          disabled={busyId === copy.id}
                        >
                          Marcar disponible
                        </button>
                      ) : (
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => changeStatus(copy, "lost")}
                          disabled={busyId === copy.id}
                        >
                          Marcar perdido
                        </button>
                      )}
                      <button
                        className="btn btn-danger btn-sm"
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
