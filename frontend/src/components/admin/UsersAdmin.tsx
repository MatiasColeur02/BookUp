import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { useToast } from "../../context/ToastContext";
import { useSession } from "../../context/SessionContext";
import { roleLabel } from "../../lib/roles";
import type { Library, User } from "../../types";
import { ErrorBanner } from "../ErrorBanner";
import { UserForm } from "./UserForm";
import { TableSkeleton } from "../Skeleton";

type FormState = { mode: "hidden" } | { mode: "create" } | { mode: "edit"; user: User };

export function UsersAdmin() {
  const { user: me, refresh } = useSession();
  const toast = useToast();

  const [users, setUsers] = useState<User[]>([]);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [form, setForm] = useState<FormState>({ mode: "hidden" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextUsers, nextLibraries] = await Promise.all([api.users.list(), api.libraries.list()]);
      setUsers(nextUsers);
      setLibraries(nextLibraries);
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
    // Bajar a alguien de rol le limpia el `library_id` en la API; si el editado era
    // uno mismo, el contexto de sesión también quedó viejo.
    await refresh();
  };

  const handleRemove = async (user: User) => {
    if (!window.confirm(`¿Eliminar al usuario «${user.name}»?`)) return;
    setError(null);
    try {
      await api.users.remove(user.id);
      toast.success(`Se eliminó a «${user.name}».`);
      await load();
    } catch (err) {
      toast.error(err);
    }
  };

  const libraryName = (id: number | null) =>
    id === null ? "—" : libraries.find((library) => library.id === id)?.name ?? `#${id}`;

  return (
    <section className="stack">
      <div className="page-header">
        <h2>Usuarios</h2>
        {form.mode === "hidden" && (
          <button className="btn btn-primary" onClick={() => setForm({ mode: "create" })}>
            Alta de personal
          </button>
        )}
      </div>
      <p className="hint">
        El registro público solo crea clientes. Los bibliotecarios y administradores se dan de alta
        desde acá, y una sede a cargo solo tiene sentido para el personal de sede.
      </p>

      <ErrorBanner error={error} />

      {form.mode !== "hidden" && (
        <UserForm
          key={form.mode === "edit" ? form.user.id : "nuevo"}
          user={form.mode === "edit" ? form.user : undefined}
          libraries={libraries}
          onSaved={handleSaved}
          onCancel={() => setForm({ mode: "hidden" })}
        />
      )}

      {loading ? (
        <TableSkeleton />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Id</th>
                <th>Nombre</th>
                <th>Email</th>
                <th>Rol</th>
                <th>Sede</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <span className="badge badge-neutral">#{user.id}</span>
                  </td>
                  <td>{user.name}</td>
                  <td>{user.email}</td>
                  <td>
                    <span className="badge badge-neutral">{roleLabel(user.role)}</span>
                  </td>
                  <td>{libraryName(user.library_id)}</td>
                  <td>
                    <div className="row-actions">
                      <button className="btn btn-secondary btn-sm" onClick={() => setForm({ mode: "edit", user })}>
                        Editar
                      </button>
                      {/* Borrarse a uno mismo cierra la sesión: se hace desde el perfil. */}
                      {user.id !== me?.id && (
                        <button className="btn btn-danger btn-sm" onClick={() => handleRemove(user)}>
                          Eliminar
                        </button>
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
