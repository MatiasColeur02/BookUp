import { useEffect, useState } from "react";
import { api } from "../api";
import type { Library } from "../types";
import { ErrorBanner } from "./ErrorBanner";
import { PinIcon } from "./icons";

/** Listado público de sedes: no requiere sesión. */
export function LibrariesView() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.libraries
      .list()
      .then(setLibraries)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="muted">Cargando sedes...</p>;

  return (
    <div className="libraries-view">
      <h2>Sedes</h2>
      <ErrorBanner error={error} />

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
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
