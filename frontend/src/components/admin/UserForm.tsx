import { useState, type FormEvent } from "react";
import { api } from "../../api";
import { useToast } from "../../context/ToastContext";
import { roleLabel } from "../../lib/roles";
import type { Library, User, UserRole, UserUpdate } from "../../types";
import { ErrorBanner } from "../ErrorBanner";

const ROLES: UserRole[] = ["customer", "librarian", "sysadmin"];

interface Props {
  /** `undefined` = alta de personal (`POST /users/staff`); con un usuario = edición. */
  user?: User;
  libraries: Library[];
  onSaved: () => void;
  onCancel: () => void;
}

export function UserForm({ user, libraries, onSaved, onCancel }: Props) {
  const toast = useToast();
  const editing = user !== undefined;

  const [email, setEmail] = useState(user?.email ?? "");
  const [password, setPassword] = useState("");
  const [name, setName] = useState(user?.name ?? "");
  const [language, setLanguage] = useState(user?.language ?? "es");
  const [role, setRole] = useState<UserRole>(user?.role ?? "librarian");
  const [libraryId, setLibraryId] = useState<string>(user?.library_id?.toString() ?? "");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // `library_id` solo es válido junto con `role=librarian`: cualquier otra combinación
  // da 409, así que el selector se apaga y se limpia al cambiar de rol.
  const canHaveLibrary = role === "librarian";

  const handleRoleChange = (next: UserRole) => {
    setRole(next);
    if (next !== "librarian") setLibraryId("");
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const library_id = canHaveLibrary && libraryId !== "" ? Number(libraryId) : null;

      if (editing) {
        const payload: UserUpdate = { name, language, role, library_id };
        if (password) payload.password = password;
        const saved = await api.users.update(user.id, payload);
        toast.success(`«${saved.name}» actualizado.`);
      } else {
        const saved = await api.users.createStaff({
          email,
          password,
          name,
          language,
          role,
          library_id,
        });
        toast.success(`«${saved.name}» dado de alta.`);
      }
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="form-card" onSubmit={handleSubmit}>
      <h3>{editing ? `Editar «${user.name}»` : "Alta de personal"}</h3>

      <ErrorBanner
        error={error}
        overrides={{
          409: "Ese email ya está registrado, o la combinación de rol y sede no es válida.",
          404: "La sede elegida no existe. Recargá la página.",
        }}
      />

      <label>
        Email
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          disabled={editing}
          required
        />
        {editing && <span className="field-hint">El email no se puede cambiar desde acá.</span>}
      </label>

      <label>
        Nombre
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>

      <label>
        {editing ? "Nueva contraseña" : "Contraseña"}
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          minLength={8}
          placeholder={editing ? "Dejala vacía para no cambiarla" : "Al menos 8 caracteres"}
          required={!editing}
        />
      </label>

      <label>
        Idioma
        <select value={language} onChange={(event) => setLanguage(event.target.value)}>
          <option value="es">Español</option>
          <option value="en">Inglés</option>
        </select>
      </label>

      <label>
        Rol
        <select value={role} onChange={(event) => handleRoleChange(event.target.value as UserRole)}>
          {ROLES.map((value) => (
            <option key={value} value={value}>
              {roleLabel(value)}
            </option>
          ))}
        </select>
      </label>

      <label>
        Sede a cargo
        <select
          value={libraryId}
          onChange={(event) => setLibraryId(event.target.value)}
          disabled={!canHaveLibrary}
          required={canHaveLibrary}
        >
          <option value="">{canHaveLibrary ? "Elegir..." : "Solo aplica al personal de sede"}</option>
          {libraries.map((library) => (
            <option key={library.id} value={library.id}>
              {library.name}
            </option>
          ))}
        </select>
      </label>

      <div className="actions">
        <button type="button" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" disabled={submitting}>
          {submitting ? "Guardando..." : editing ? "Guardar cambios" : "Crear usuario"}
        </button>
      </div>
    </form>
  );
}
