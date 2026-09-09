import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import type { Library } from "../types";
import { ErrorBanner } from "./ErrorBanner";
import { Modal } from "./Modal";
import { PinIcon } from "./icons";
import { LibraryForm } from "./admin/LibraryForm";

type FormState = { mode: "hidden" } | { mode: "create" } | { mode: "edit"; library: Library };

/** Listado público de sedes: no requiere sesión. El alta y la edición sí. */
export function LibrariesView() {
  const { isSysadmin, isLibrarian, myLibraryId } = useSession();

  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [form, setForm] = useState<FormState>({ mode: "hidden" });

  const load = useCallback(async () => {
    try {
      setLibraries(await api.libraries.list());
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSaved = async () => {
    setForm({ mode: "hidden" });
    await load();
  };

  // Mismo alcance que `PATCH /libraries/{id}`: un sysadmin edita todas, un
  // librarian solo la suya.
  const canEdit = (library: Library) =>
    isSysadmin || (isLibrarian && myLibraryId === library.id);

  if (loading) return <p className="muted">Cargando sedes...</p>;

  return (
    <div className="libraries-view">
      <div className="page-header">
        <h2>Sedes</h2>
        {isSysadmin && (
          <button className="btn btn-primary" onClick={() => setForm({ mode: "create" })}>
            Nueva sede
          </button>
        )}
      </div>

      <ErrorBanner error={error} />

      {form.mode !== "hidden" && (
        <Modal
          title={form.mode === "edit" ? `Editar «${form.library.name}»` : "Nueva sede"}
          onClose={() => setForm({ mode: "hidden" })}
        >
          <LibraryForm
            key={form.mode === "edit" ? form.library.id : "nueva"}
            library={form.mode === "edit" ? form.library : undefined}
            onSaved={handleSaved}
            onCancel={() => setForm({ mode: "hidden" })}
          />
        </Modal>
      )}

      {libraries.length === 0 ? (
        <p className="empty">Todavía no hay sedes cargadas.</p>
      ) : (
        <ul className="library-cards">
          {libraries.map((library) => (
            <li key={library.id} className="card">
              <h3>{library.name}</h3>
              <p className="library-address">
                <PinIcon className="inline-icon" />
                {library.address}, {library.city}, {library.state}
              </p>
              <dl className="library-meta">
                {library.hours && (
                  <>
                    <dt>Horarios</dt>
                    <dd>{library.hours}</dd>
                  </>
                )}
                {library.phone && (
                  <>
                    <dt>Teléfono</dt>
                    <dd>{library.phone}</dd>
                  </>
                )}
                {library.email && (
                  <>
                    <dt>Email</dt>
                    <dd>{library.email}</dd>
                  </>
                )}
                {library.website && (
                  <>
                    <dt>Web</dt>
                    <dd>
                      <a href={library.website} target="_blank" rel="noreferrer">
                        {library.website}
                      </a>
                    </dd>
                  </>
                )}
              </dl>
              {canEdit(library) && (
                <div className="row-actions library-card-actions">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setForm({ mode: "edit", library })}
                  >
                    Editar
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
