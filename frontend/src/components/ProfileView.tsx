import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import { ErrorBanner } from "./ErrorBanner";
import { roleLabel } from "../lib/roles";
import type { Library, UserUpdate } from "../types";

const LANGUAGES = [
  { code: "es", label: "Español" },
  { code: "en", label: "Inglés" },
];

export function ProfileView() {
  const { user, refresh, logout, isSysadmin } = useSession();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("es");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  // La sede a cargo: solo la tiene un librarian (y un sysadmin si se le asignó una).
  const [library, setLibrary] = useState<Library | null>(null);

  const userId = user?.id;
  const libraryId = user?.library_id ?? null;

  useEffect(() => {
    if (libraryId === null) {
      setLibrary(null);
      return;
    }
    let cancelled = false;
    api.libraries
      .get(libraryId)
      // Si la sede no se puede leer, se cae al texto sin nombre: es un dato de contexto,
      // no vale romper el perfil por él.
      .then((next) => {
        if (!cancelled) setLibrary(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [libraryId]);

  useEffect(() => {
    if (userId === undefined) return;
    let cancelled = false;
    setLoading(true);
    api.users
      .get(userId)
      .then((me) => {
        if (cancelled) return;
        setName(me.name);
        setLanguage(me.language);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (!user) return null;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSaved(false);
    try {
      // Solo los campos que el usuario puede tocar sobre sí mismo: mandar `role` o
      // `library_id` siendo `customer` devuelve 403, así que ni se exponen acá.
      const payload: UserUpdate = { name, language };
      if (password) payload.password = password;

      await api.users.update(user.id, payload);
      await refresh();
      setPassword("");
      setSaved(true);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    logout();
    // Sin sesión, `/perfil` rebota a `/login` (RequireRole): mejor salir al catálogo.
    navigate("/", { replace: true });
  };

  const handleDelete = async () => {
    const confirmed = window.confirm(
      "¿Eliminar tu cuenta? Se cierra la sesión y no se puede deshacer."
    );
    if (!confirmed) return;

    setError(null);
    try {
      await api.users.remove(user.id);
      logout();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div className="profile-view">
      <form className="form-card" onSubmit={handleSubmit}>
        <h2>Mi perfil</h2>
        <p className="hint">
          {user.email} · {roleLabel(user.role)}
        </p>

        {/* Alcance de lo que administra. Un customer no administra nada: no se muestra. */}
        {libraryId !== null ? (
          <p className="scope-note">
            {isSysadmin ? "Sysadmin asignado a" : "Bibliotecario a cargo de"}{" "}
            <strong>{library?.name ?? `la sede #${libraryId}`}</strong>
            {library && ` · ${library.city}, ${library.state}`}
          </p>
        ) : (
          isSysadmin && (
            <p className="scope-note">
              Administrás <strong>todas las sedes</strong> de la red.
            </p>
          )
        )}

        <ErrorBanner error={error} />
        {saved && <p className="success">Perfil actualizado.</p>}

        {loading ? (
          <p className="muted">Cargando perfil...</p>
        ) : (
          <>
            <label>
              Nombre
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Idioma
              <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                {LANGUAGES.map(({ code, label }) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Nueva contraseña
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                minLength={8}
                placeholder="Dejala vacía para no cambiarla"
              />
            </label>
            <div className="actions">
              <button type="button" className="row-button" onClick={handleLogout}>
                Cerrar sesión
              </button>
              <button type="submit" disabled={submitting}>
                {submitting ? "Guardando..." : "Guardar cambios"}
              </button>
            </div>
          </>
        )}
      </form>

      <div className="form-card danger-zone">
        <h3>Eliminar mi cuenta</h3>
        <p className="hint">
          Se borra tu usuario de forma permanente. Tus reservas cerradas quedan en el historial de
          la sede.
        </p>
        <div className="actions">
          <button type="button" className="danger-button" onClick={handleDelete}>
            Eliminar mi cuenta
          </button>
        </div>
      </div>
    </div>
  );
}
