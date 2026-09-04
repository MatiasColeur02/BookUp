export interface Library {
  id: number;
  name: string;
  city: string;
  address: string | null;
}

export interface Book {
  id: number;
  title: string;
  author: string;
  isbn: string;
  synopsis: string | null;
}

export interface LibraryAvailability {
  library: Library;
  available_copies: number;
  copy_id: number;
}

export interface BookAvailability {
  book: Book;
  libraries: LibraryAvailability[];
}

export type ReservationStatus = "pending" | "confirmed" | "cancelled" | "fulfilled";

export interface Reservation {
  id: number;
  copy_id: number;
  patron_name: string;
  patron_email: string;
  status: ReservationStatus;
  created_at: string;
  confirmed_by: string | null;
}
