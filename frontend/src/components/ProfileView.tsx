import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import { describeError } from "../lib/errors";
import { roleLabel } from "../lib/roles";
import type { UserUpdate } from "../types";

const LANGUAGES = [
  { code: "es", label: "Español" },
  { code: "en", label: "Inglés" },
];

export function ProfileView() {
  const { user, refresh, logout } = useSession();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("es");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const userId = user?.id;

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
        if (!cancelled) setError(describeError(err));
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
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
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
      setError(describeError(err));
    }
  };

  return (
    <div className="profile-view">
      <form className="form-card" onSubmit={handleSubmit}>
        <h2>Mi perfil</h2>
        <p className="hint">
          {user.email} · {roleLabel(user.role)}
        </p>

        {error && <p className="error">{error}</p>}
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
