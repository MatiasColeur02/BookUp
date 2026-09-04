import type { Book, BookAvailability, Reservation } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed with status ${res.status}`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  searchBooks: (query: string) => request<Book[]>(`/books/search?q=${encodeURIComponent(query)}`),

  getAvailability: (bookId: number) => request<BookAvailability>(`/books/${bookId}/availability`),

  createReservation: (payload: { copy_id: number; patron_name: string; patron_email: string }) =>
    request<Reservation>("/reservations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listReservations: (libraryId?: number) =>
    request<Reservation[]>(`/reservations${libraryId ? `?library_id=${libraryId}` : ""}`),

  confirmReservation: (reservationId: number, librarian: string) =>
    request<Reservation>(`/reservations/${reservationId}/confirm?librarian=${encodeURIComponent(librarian)}`, {
      method: "PATCH",
    }),
};
