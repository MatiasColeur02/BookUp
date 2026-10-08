/**
 * Espejo de los topes que valida la API (esquemas Pydantic en
 * `api/app/controllers/schemas.py`).
 *
 * Acá son una cortesía, no una defensa: el `maxLength` de un input evita que alguien
 * escriba 400 caracteres para recibir un 422 recién al enviar, pero cualquiera puede
 * saltearlo con curl. La validación que cuenta es la del backend, y por eso los números
 * viven en los dos lados en vez de solo acá.
 *
 * Si cambia un tope en la API, cambiarlo también acá.
 */
export const LIMITS = {
  library: {
    name: 150,
    address: 255,
    state: 100,
    city: 100,
    hours: 255,
    phone: 50,
    email: 255,
    website: 255,
  },
  book: {
    isbn: 13,
    title: 255,
    language: 50,
    synopsis: 5000,
    /** `pages` no tiene columna que lo acote: el rango lo pone el dominio. */
    pagesMin: 1,
    pagesMax: 50000,
  },
  author: { name: 200 },
  genre: { name: 100 },
  user: {
    name: 150,
    email: 255,
    language: 10,
    passwordMin: 8,
    /**
     * bcrypt solo mira los primeros 72 bytes y descarta el resto sin avisar, así que la
     * API rechaza lo que pase de ahí en vez de truncar en silencio. El input cuenta
     * caracteres y no bytes: un acento ocupa dos, de ahí que el backend siga siendo la
     * validación real.
     */
    passwordMax: 72,
  },
  /** Texto libre del buscador del catálogo. */
  searchQuery: 200,
  /** Ventana máxima de una reserva, en días. */
  reservationDays: 365,
} as const;
