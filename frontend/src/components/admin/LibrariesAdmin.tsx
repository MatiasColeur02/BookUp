import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { useSession } from "../../context/SessionContext";
import { describeError } from "../../lib/errors";
import type { Library } from "../../types";
import { ErrorBanner } from "../ErrorBanner";
import { LibraryForm } from "./LibraryForm";

type FormState = { mode: "hidden" } | { mode: "create" } | { mode: "edit"; library: Library };

export function LibrariesAdmin() {
  const { isSysadmin, myLibraryId } = useSession();

  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [form, setForm] = useState<FormState>({ mode: "hidden" });

  const load = useCallback(async () => {
    setLoading(true);
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

  const handleRemove = async (library: Library) => {
    if (!window.confirm(`¿Eliminar la sede «${library.name}»?`)) return;
    setError(null);
    try {
      await api.libraries.remove(library.id);
      await load();
    } catch (err) {
      setError(
        describeError(err, {
          409: "No se puede eliminar: la sede todavía tiene ejemplares. Dalos de baja desde «Ejemplares» primero.",
        })
      );
    }
  };

  // Un `librarian` solo administra su propia sede: sin alta ni baja.
  if (!isSysadmin) {
    const mine = libraries.find((library) => library.id === myLibraryId);

    return (
      <section className="librarian-panel">
        <h2>Mi sede</h2>
        <ErrorBanner error={error} />
        {loading ? (
          <p className="muted">Cargando sede...</p>
        ) : mine ? (
          <LibraryForm key={mine.id} library={mine} onSaved={load} />
        ) : (
          <p className="empty">No tenés una sede asignada. Pedile a un administrador que te asigne una.</p>
        )}
      </section>
    );
  }

  return (
    <section className="librarian-panel">
      <div className="panel-filters">
        <h2>Sedes</h2>
        {form.mode === "hidden" && (
          <button className="confirm-button" onClick={() => setForm({ mode: "create" })}>
            Nueva sede
          </button>
        )}
      </div>

      <ErrorBanner error={error} />

      {form.mode !== "hidden" && (
        <LibraryForm
          key={form.mode === "edit" ? form.library.id : "nueva"}
          library={form.mode === "edit" ? form.library : undefined}
          onSaved={handleSaved}
          onCancel={() => setForm({ mode: "hidden" })}
        />
      )}

      {loading ? (
        <p className="muted">Cargando sedes...</p>
      ) : libraries.length === 0 ? (
        <p className="empty">Todavía no hay sedes. Creá la primera para poder cargarle ejemplares.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Id</th>
                <th>Nombre</th>
                <th>Ciudad</th>
                <th>Contacto</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {libraries.map((library) => (
                <tr key={library.id}>
                  <td>
                    <span className="badge">#{library.id}</span>
                  </td>
                  <td>{library.name}</td>
                  <td>
                    {library.city}, {library.state}
                  </td>
                  <td>{library.phone ?? library.email ?? "—"}</td>
                  <td>
                    <div className="row-actions">
                      <button className="row-button" onClick={() => setForm({ mode: "edit", library })}>
                        Editar
                      </button>
                      <button className="row-button danger" onClick={() => handleRemove(library)}>
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
