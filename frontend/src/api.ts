import { clearToken, getToken } from "./lib/session";
import type {
  Author,
  AuthorCreate,
  AuthorUpdate,
  Book,
  BookAvailability,
  BookCreate,
  BookUpdate,
  ExpiredReservations,
  Genre,
  GenreCreate,
  GenreUpdate,
  Library,
  LibraryCreate,
  LibraryUpdate,
  LoginRequest,
  PhysicalBook,
  PhysicalBookCreate,
  PhysicalBookStatus,
  PhysicalBookStatusUpdate,
  Reservation,
  ReservationCreate,
  ReservationUpdate,
  TokenOut,
  User,
  UserCreate,
  UserStaffCreate,
  UserUpdate,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Un campo inválido devuelto por el 422 de FastAPI/Pydantic. */
export interface FieldError {
  field: string;
  message: string;
}

/**
 * Error con el status HTTP a la vista, para que la UI pueda distinguir un 409
 * (conflicto de negocio, con un `detail` ya redactado por la API) de un 422
 * (validación) o de un 403 (permisos) en vez de mostrar todo igual.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  /** Solo en los 422: los campos que Pydantic rechazó. */
  readonly fields: FieldError[];

  constructor(status: number, detail: string, fields: FieldError[] = []) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.fields = fields;
  }
}

/** Falla de red / API caída: no hubo respuesta HTTP, así que no hay status. */
export class NetworkError extends Error {
  constructor() {
    super("No pudimos conectarnos con el servidor.");
    this.name = "NetworkError";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** `false` en los endpoints públicos: nunca mandan `Authorization`. */
  auth?: boolean;
}

type QueryParams = Record<string, string | number | boolean | undefined>;

function buildQuery(params: QueryParams): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/**
 * El 422 de FastAPI viene como `{ detail: [{ loc, msg, type }] }` — un array, no un
 * string. Sin esto el mensaje termina siendo "[object Object]".
 */
function parseValidationError(detail: unknown): FieldError[] {
  if (!Array.isArray(detail)) return [];
  return detail.map((item) => {
    const loc = Array.isArray(item?.loc) ? item.loc : [];
    // El primer segmento es siempre "body"/"query"/"path": el campo es el resto.
    const field = loc.slice(1).join(".") || loc.join(".") || "payload";
    return { field, message: typeof item?.msg === "string" ? item.msg : "Valor inválido" };
  });
}

async function toApiError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null);
  const detail = body?.detail;

  if (res.status === 422) {
    const fields = parseValidationError(detail);
    const summary = fields.map((f) => `${f.field}: ${f.message}`).join("; ");
    return new ApiError(422, summary || "Los datos enviados no son válidos.", fields);
  }
  if (typeof detail === "string") return new ApiError(res.status, detail);
  return new ApiError(res.status, `La petición falló con status ${res.status}.`);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const token = auth ? getToken() : null;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new NetworkError();
  }

  if (!res.ok) {
    // Interceptor de 401: si mandamos un token y la API lo rechazó, la sesión murió
    // (vencida, revocada, o el usuario fue borrado). Limpiarlo acá hace que el
    // contexto de sesión se entere y la app vuelva sola al estado deslogueado, en vez
    // de dejar un error suelto en pantalla con un token muerto guardado.
    if (res.status === 401 && token) clearToken();
    throw await toApiError(res);
  }

  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  health: () => request<{ status: string }>("/health", { auth: false }),

  auth: {
    login: (payload: LoginRequest) =>
      request<TokenOut>("/auth/login", { method: "POST", body: payload, auth: false }),

    me: () => request<User>("/auth/me"),
  },

  users: {
    list: () => request<User[]>("/users"),

    get: (userId: number) => request<User>(`/users/${userId}`),

    /** Auto-registro público: el rol siempre queda en `customer`. */
    create: (payload: UserCreate) =>
      request<User>("/users", { method: "POST", body: payload, auth: false }),

    /** Alta de personal (`librarian`/`sysadmin`); solo `sysadmin`. */
    createStaff: (payload: UserStaffCreate) =>
      request<User>("/users/staff", { method: "POST", body: payload }),

    update: (userId: number, payload: UserUpdate) =>
      request<User>(`/users/${userId}`, { method: "PATCH", body: payload }),

    remove: (userId: number) => request<void>(`/users/${userId}`, { method: "DELETE" }),
  },

  books: {
    list: () => request<Book[]>("/books", { auth: false }),

    search: (query: string) =>
      request<Book[]>(`/books/search${buildQuery({ q: query })}`, { auth: false }),

    get: (isbn: string) => request<Book>(`/books/${encodeURIComponent(isbn)}`, { auth: false }),

    availability: (isbn: string) =>
      request<BookAvailability>(`/books/${encodeURIComponent(isbn)}/availability`, { auth: false }),

    create: (payload: BookCreate) => request<Book>("/books", { method: "POST", body: payload }),

    update: (isbn: string, payload: BookUpdate) =>
      request<Book>(`/books/${encodeURIComponent(isbn)}`, { method: "PATCH", body: payload }),

    remove: (isbn: string) =>
      request<void>(`/books/${encodeURIComponent(isbn)}`, { method: "DELETE" }),
  },

  authors: {
    list: () => request<Author[]>("/authors", { auth: false }),

    get: (authorId: number) => request<Author>(`/authors/${authorId}`, { auth: false }),

    create: (payload: AuthorCreate) => request<Author>("/authors", { method: "POST", body: payload }),

    update: (authorId: number, payload: AuthorUpdate) =>
      request<Author>(`/authors/${authorId}`, { method: "PATCH", body: payload }),

    remove: (authorId: number) => request<void>(`/authors/${authorId}`, { method: "DELETE" }),
  },

  genres: {
    list: () => request<Genre[]>("/genres", { auth: false }),

    get: (genreId: number) => request<Genre>(`/genres/${genreId}`, { auth: false }),

    create: (payload: GenreCreate) => request<Genre>("/genres", { method: "POST", body: payload }),

    update: (genreId: number, payload: GenreUpdate) =>
      request<Genre>(`/genres/${genreId}`, { method: "PATCH", body: payload }),

    remove: (genreId: number) => request<void>(`/genres/${genreId}`, { method: "DELETE" }),
  },

  libraries: {
    list: () => request<Library[]>("/libraries", { auth: false }),

    get: (libraryId: number) => request<Library>(`/libraries/${libraryId}`, { auth: false }),

    create: (payload: LibraryCreate) =>
      request<Library>("/libraries", { method: "POST", body: payload }),

    update: (libraryId: number, payload: LibraryUpdate) =>
      request<Library>(`/libraries/${libraryId}`, { method: "PATCH", body: payload }),

    remove: (libraryId: number) => request<void>(`/libraries/${libraryId}`, { method: "DELETE" }),
  },

  physicalBooks: {
    list: (filters: { isbn?: string; library_id?: number; status?: PhysicalBookStatus } = {}) =>
      request<PhysicalBook[]>(`/physical-books${buildQuery(filters)}`, { auth: false }),

    get: (physicalBookId: number) =>
      request<PhysicalBook>(`/physical-books/${physicalBookId}`, { auth: false }),

    create: (payload: PhysicalBookCreate) =>
      request<PhysicalBook>("/physical-books", { method: "POST", body: payload }),

    /** Solo admite `available` y `lost`: el resto lo maneja el flujo de reservas. */
    updateStatus: (physicalBookId: number, payload: PhysicalBookStatusUpdate) =>
      request<PhysicalBook>(`/physical-books/${physicalBookId}/status`, {
        method: "PATCH",
        body: payload,
      }),

    remove: (physicalBookId: number) =>
      request<void>(`/physical-books/${physicalBookId}`, { method: "DELETE" }),
  },

  reservations: {
    /**
     * El alcance lo define el rol del token: propias, de la sede, o todas.
     * `mine: true` lo cambia por "las del usuario del token" sin importar el rol —
     * necesario para un `librarian`/`sysadmin`, cuyo alcance por rol no incluye sus
     * propias reservas si están en otra sede.
     */
    list: (filters: { library_id?: number; is_open?: boolean; mine?: boolean } = {}) =>
      request<Reservation[]>(`/reservations${buildQuery(filters)}`),

    get: (reservationId: number) => request<Reservation>(`/reservations/${reservationId}`),

    /** El dueño sale del token: `user_id` no va en el body. */
    create: (payload: ReservationCreate) =>
      request<Reservation>("/reservations", { method: "POST", body: payload }),

    /** Extender el vencimiento. */
    update: (reservationId: number, payload: ReservationUpdate) =>
      request<Reservation>(`/reservations/${reservationId}`, { method: "PATCH", body: payload }),

    cancel: (reservationId: number) =>
      request<Reservation>(`/reservations/${reservationId}/cancel`, { method: "POST" }),

    markPickedUp: (reservationId: number) =>
      request<Reservation>(`/reservations/${reservationId}/pickup`, { method: "PATCH" }),

    markReturned: (reservationId: number) =>
      request<Reservation>(`/reservations/${reservationId}/return`, { method: "PATCH" }),

    /** Idempotente, solo `sysadmin`: cierra las vencidas que nunca se retiraron. */
    expire: () => request<ExpiredReservations>("/reservations/expire", { method: "POST" }),
  },
};
