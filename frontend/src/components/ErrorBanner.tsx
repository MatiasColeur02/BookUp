import { ApiError } from "../api";
import { describeError } from "../lib/errors";

interface Props {
  /**
   * El error tal como vino (`ApiError`, `NetworkError`, …) o un mensaje ya redactado.
   * Aceptar las dos formas evita reescribir las pantallas que ya arman su mensaje con
   * `describeError` y sus propios overrides por acción.
   */
  error: unknown;
  /** Mensajes por status, cuando se le pasa el error crudo. */
  overrides?: Partial<Record<number, string>>;
}

export function ErrorBanner({ error, overrides }: Props) {
  if (error === null || error === undefined || error === "") return null;

  const message = typeof error === "string" ? error : describeError(error, overrides);
  // El 422 llega con la lista de campos que Pydantic rechazó: mostrarlos uno por uno
  // es más útil que concatenarlos en una sola línea.
  const fields = error instanceof ApiError && error.status === 422 ? error.fields : [];

  return (
    <div className="error" role="alert">
      {fields.length > 0 ? (
        <>
          <p>Revisá los datos enviados:</p>
          <ul>
            {fields.map((field) => (
              <li key={field.field}>
                <strong>{field.field}</strong>: {field.message}
              </li>
            ))}
          </ul>
        </>
      ) : (
        message
      )}
    </div>
  );
}
