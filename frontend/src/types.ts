// Contrato con la API. Espeja `api/openapi.yml`: cada interfaz `*Out` lleva todos
// los campos que declara el spec, incluidos los nullable, y cada `*Create`/`*Update`
// es el payload exacto que espera el endpoint.

export interface Library {
  id: number;
  name: string;
  address: string;
  state: string;
  city: string;
  hours: string | null;
  phone: string | null;
  email: string | null;
  website: string | null;
}

export interface LibraryCreate {
  name: string;
  address: string;
  state: string;
  city: string;
  hours?: string | null;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
}

// Un campo enviado en `null` se ignora (no borra el valor existente): para vaciar un
// campo opcional hay que mandar "".
export type LibraryUpdate = Partial<LibraryCreate>;

export interface Author {
  id: number;
  name: string;
}

export interface AuthorCreate {
  name: string;
}

export type AuthorUpdate = Partial<AuthorCreate>;

export interface Genre {
  id: number;
  name: string;
}

export interface GenreCreate {
  name: string;
}

export type GenreUpdate = Partial<GenreCreate>;

export interface Book {
  isbn: string;
  title: string;
  language: string;
  pages: number | null;
  synopsis: string | null;
  authors: Author[];
  genres: Genre[];
}

export interface BookCreate {
  isbn: string;
  title: string;
  language: string;
  pages?: number | null;
  synopsis?: string | null;
  author_ids?: number[];
  genre_ids?: number[];
}

// `author_ids`/`genre_ids` reemplazan la lista completa cuando se envían.
export interface BookUpdate {
  title?: string | null;
  language?: string | null;
  pages?: number | null;
  synopsis?: string | null;
  author_ids?: number[] | null;
  genre_ids?: number[] | null;
}

export interface LibraryAvailability {
  library: Library;
  available_copies: number;
  physical_book_id: number;
}

export interface BookAvailability {
  book: Book;
  libraries: LibraryAvailability[];
}

export type PhysicalBookStatus = "available" | "reserved" | "loaned" | "lost";

export interface PhysicalBook {
  id: number;
  isbn: string;
  library_id: number;
  status: PhysicalBookStatus;
}

export interface PhysicalBookCreate {
  isbn: string;
  library_id: number;
}

// La API solo acepta `available` y `lost` como destino manual: `reserved`/`loaned`
// los maneja el flujo de reservas y pedirlos da 409.
export type ManualPhysicalBookStatus = Extract<PhysicalBookStatus, "available" | "lost">;

export interface PhysicalBookStatusUpdate {
  status: ManualPhysicalBookStatus;
}

export type UserRole = "customer" | "librarian" | "sysadmin";

export interface User {
  id: number;
  email: string;
  name: string;
  language: string;
  role: UserRole;
  library_id: number | null;
}

// Auto-registro público: el rol siempre queda en `customer`.
export interface UserCreate {
  email: string;
  password: string;
  name: string;
  language?: string;
}

// Alta de personal, solo `sysadmin`. `library_id` solo es válido con `role=librarian`.
export interface UserStaffCreate extends UserCreate {
  role: UserRole;
  library_id?: number | null;
}

export interface UserUpdate {
  name?: string | null;
  language?: string | null;
  password?: string | null;
  role?: UserRole | null;
  library_id?: number | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// No hay enum de estado: la reserva está abierta mientras `cancelled_at` y
// `returned_at` sean null, y `picked_up` distingue las dos etapas abiertas.
export interface Reservation {
  id: number;
  user_id: number;
  physical_book_id: number;
  reserved_at: string;
  expires_at: string;
  picked_up: boolean;
  cancelled_at: string | null;
  returned_at: string | null;
}

// El dueño sale del token: `user_id` no se envía.
export interface ReservationCreate {
  physical_book_id: number;
  expires_at: string;
}

export interface ReservationUpdate {
  expires_at?: string | null;
}

export interface ExpiredReservations {
  expired: number;
}
