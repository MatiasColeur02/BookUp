import type { Book, BookAvailability, Reservation, User } from "./types";

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

  getAvailability: (isbn: string) => request<BookAvailability>(`/books/${encodeURIComponent(isbn)}/availability`),

  createUser: (payload: { email: string; password: string; name: string; language?: string }) =>
    request<User>("/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createReservation: (payload: { physical_book_id: number; user_id: number; expires_at: string }) =>
    request<Reservation>("/reservations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listReservations: (libraryId?: number) =>
    request<Reservation[]>(`/reservations${libraryId ? `?library_id=${libraryId}` : ""}`),

  markPickedUp: (reservationId: number) =>
    request<Reservation>(`/reservations/${reservationId}/pickup`, {
      method: "PATCH",
    }),
};
