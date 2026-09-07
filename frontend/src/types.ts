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

export interface Author {
  id: number;
  name: string;
}

export interface Genre {
  id: number;
  name: string;
}

export interface Book {
  isbn: string;
  title: string;
  language: string;
  pages: number | null;
  synopsis: string | null;
  authors: Author[];
  genres: Genre[];
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

export type UserRole = "customer" | "librarian" | "sysadmin";

export interface User {
  id: number;
  email: string;
  name: string;
  language: string;
  role: UserRole;
  library_id: number | null;
}

export interface Reservation {
  id: number;
  user_id: number;
  physical_book_id: number;
  reserved_at: string;
  expires_at: string;
  picked_up: boolean;
}
