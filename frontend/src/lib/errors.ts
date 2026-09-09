import { ApiError, NetworkError } from "../api";

const DEFAULT_MESSAGES: Partial<Record<number, string>> = {
  401: "Tu sesión venció. Iniciá sesión de nuevo.",
  403: "No tenés permiso para hacer esto.",
  404: "No se encontró lo que buscabas.",
  // El cuerpo del request pasó el techo de la API (`MAX_REQUEST_BYTES`).
  413: "Lo que enviaste es demasiado grande.",
  // Rate limit: la API frena los intentos de login y las altas de cuenta por IP.
  429: "Demasiados intentos. Esperá unos minutos y volvé a probar.",
};

/**
 * Traduce un error de `api.ts` a un mensaje para mostrar en pantalla. `overrides`
 * deja que cada acción redacte su propio mensaje de conflicto (409): el mismo status
 * significa algo distinto según qué se estaba haciendo.
 */
export function describeError(error: unknown, overrides: Partial<Record<number, string>> = {}): string {
  if (error instanceof ApiError) {
    return overrides[error.status] ?? DEFAULT_MESSAGES[error.status] ?? error.detail;
  }
  if (error instanceof NetworkError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Ocurrió un error inesperado.";
}
