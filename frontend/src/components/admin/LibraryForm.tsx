import { useState, type FormEvent } from "react";
import { api } from "../../api";
import type { Library } from "../../types";
import { ErrorBanner } from "../ErrorBanner";

interface Props {
  /** `undefined` = alta (solo `sysadmin`); con una sede = edición. */
  library?: Library;
  onSaved: () => void;
  onCancel?: () => void;
}

export function LibraryForm({ library, onSaved, onCancel }: Props) {
  const editing = library !== undefined;

  const [name, setName] = useState(library?.name ?? "");
  const [address, setAddress] = useState(library?.address ?? "");
  const [state, setState] = useState(library?.state ?? "");
  const [city, setCity] = useState(library?.city ?? "");
  const [hours, setHours] = useState(library?.hours ?? "");
  const [phone, setPhone] = useState(library?.phone ?? "");
  const [email, setEmail] = useState(library?.email ?? "");
  const [website, setWebsite] = useState(library?.website ?? "");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      // Los opcionales van como "" y no como null: en el PATCH la API **ignora** los
      // campos enviados en null, así que mandar null nunca borraría un valor viejo.
      const fields = { name, address, state, city, hours, phone, email, website };

      if (editing) {
        await api.libraries.update(library.id, fields);
      } else {
        await api.libraries.create(fields);
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
      <h3>{editing ? `Editar «${library.name}»` : "Nueva sede"}</h3>

      <ErrorBanner error={error} />

      <label>
        Nombre
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <label>
        Dirección
        <input value={address} onChange={(event) => setAddress(event.target.value)} required />
      </label>
      <label>
        Ciudad
        <input value={city} onChange={(event) => setCity(event.target.value)} required />
      </label>
      <label>
        Provincia
        <input value={state} onChange={(event) => setState(event.target.value)} required />
      </label>
      <label>
        Horarios
        <input
          value={hours}
          onChange={(event) => setHours(event.target.value)}
          placeholder="Opcional. Ej: L-V 9 a 18"
        />
      </label>
      <label>
        Teléfono
        <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Opcional" />
      </label>
      <label>
        Email
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Opcional"
        />
      </label>
      <label>
        Sitio web
        <input value={website} onChange={(event) => setWebsite(event.target.value)} placeholder="Opcional" />
      </label>

      <div className="actions">
        {onCancel && (
          <button type="button" onClick={onCancel} disabled={submitting}>
            Cancelar
          </button>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? "Guardando..." : editing ? "Guardar cambios" : "Crear sede"}
        </button>
      </div>
    </form>
  );
}
