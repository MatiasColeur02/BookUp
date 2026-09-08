import { useCallback, useEffect, useState, type FormEvent } from "react";
import { describeError } from "../../lib/errors";
import { ErrorBanner } from "../ErrorBanner";

export interface NamedResource {
  id: number;
  name: string;
}

interface Props {
  title: string;
  /** Explica la regla de unicidad del recurso, que no es la misma para los dos. */
  hint: string;
  singular: string;
  list: () => Promise<NamedResource[]>;
  create: (name: string) => Promise<NamedResource>;
  update: (id: number, name: string) => Promise<NamedResource>;
  remove: (id: number) => Promise<void>;
  /** Mensaje para el 409 al crear/renombrar. Sin esto el nombre no es único. */
  duplicateMessage?: string;
  /** Mensaje para el 409 al borrar (el recurso sigue asociado a un libro). */
  inUseMessage: string;
}

/**
 * `Author` y `Genre` son el mismo CRUD sobre `{ id, name }`: la única diferencia real
 * es que `Genre.name` es único en el modelo y `Author.name` no. En vez de duplicar la
 * pantalla, se parametriza esa diferencia.
 */
export function NameResourceAdmin({
  title,
  hint,
  singular,
  list,
  create,
  update,
  remove,
  duplicateMessage,
  inUseMessage,
}: Props) {
  const [items, setItems] = useState<NamedResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await list());
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [list]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await create(newName.trim());
      setNewName("");
      await load();
    } catch (err) {
      setError(describeError(err, duplicateMessage ? { 409: duplicateMessage } : {}));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRename = async (id: number) => {
    setError(null);
    try {
      await update(id, editingName.trim());
      setEditingId(null);
      await load();
    } catch (err) {
      setError(describeError(err, duplicateMessage ? { 409: duplicateMessage } : {}));
    }
  };

  const handleRemove = async (item: NamedResource) => {
    if (!window.confirm(`¿Eliminar ${singular} «${item.name}»?`)) return;
    setError(null);
    try {
      await remove(item.id);
      await load();
    } catch (err) {
      setError(describeError(err, { 409: inUseMessage }));
    }
  };

  return (
    <section className="librarian-panel">
      <h2>{title}</h2>
      <p className="hint">{hint}</p>

      <ErrorBanner error={error} />

      <form className="extend-form" onSubmit={handleCreate}>
        <label className="inline-select">
          Nombre
          <input value={newName} onChange={(event) => setNewName(event.target.value)} required />
        </label>
        <button type="submit" className="confirm-button" disabled={submitting || !newName.trim()}>
          {submitting ? "Creando..." : `Crear ${singular}`}
        </button>
      </form>

      {loading ? (
        <p className="muted">Cargando...</p>
      ) : items.length === 0 ? (
        <p className="empty">Todavía no hay nada cargado.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Id</th>
                <th>Nombre</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <span className="badge">#{item.id}</span>
                  </td>
                  <td>
                    {editingId === item.id ? (
                      <input
                        className="inline-input"
                        value={editingName}
                        onChange={(event) => setEditingName(event.target.value)}
                        autoFocus
                      />
                    ) : (
                      item.name
                    )}
                  </td>
                  <td>
                    <div className="row-actions">
                      {editingId === item.id ? (
                        <>
                          <button
                            className="confirm-button"
                            onClick={() => handleRename(item.id)}
                            disabled={!editingName.trim()}
                          >
                            Guardar
                          </button>
                          <button className="row-button" onClick={() => setEditingId(null)}>
                            Cancelar
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="row-button"
                            onClick={() => {
                              setEditingId(item.id);
                              setEditingName(item.name);
                            }}
                          >
                            Renombrar
                          </button>
                          <button className="row-button danger" onClick={() => handleRemove(item)}>
                            Eliminar
                          </button>
                        </>
                      )}
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
