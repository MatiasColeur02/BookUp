import { useState } from "react";
import { api } from "../api";
import type { Book, BookAvailability } from "../types";
import { BookAvailabilityView } from "./BookAvailabilityView";
import { BookResults } from "./BookResults";
import { ReservationForm } from "./ReservationForm";
import { SearchBar } from "./SearchBar";

const RESERVATION_WINDOW_DAYS = 7;

export function CatalogView() {
  const [results, setResults] = useState<Book[]>([]);
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [availability, setAvailability] = useState<BookAvailability | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reservingPhysicalBookId, setReservingPhysicalBookId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmationMessage, setConfirmationMessage] = useState<string | null>(null);

  const handleSearch = async (query: string) => {
    setLoading(true);
    setError(null);
    setSelectedBook(null);
    setAvailability(null);
    setConfirmationMessage(null);
    try {
      setResults(await api.searchBooks(query));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al buscar");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (book: Book) => {
    setSelectedBook(book);
    setReservingPhysicalBookId(null);
    setConfirmationMessage(null);
    try {
      setAvailability(await api.getAvailability(book.isbn));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al consultar disponibilidad");
    }
  };

  const handleReserve = async (data: { name: string; email: string; password: string }) => {
    if (reservingPhysicalBookId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      // No hay login todavía: la reserva da de alta la cuenta del usuario en el mismo paso.
      const user = await api.createUser(data);
      const expiresAt = new Date(Date.now() + RESERVATION_WINDOW_DAYS * 24 * 60 * 60 * 1000).toISOString();
      await api.createReservation({
        physical_book_id: reservingPhysicalBookId,
        user_id: user.id,
        expires_at: expiresAt,
      });
      setConfirmationMessage("Reserva creada. Retirala en la biblioteca seleccionada.");
      setReservingPhysicalBookId(null);
      if (selectedBook) {
        setAvailability(await api.getAvailability(selectedBook.isbn));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al crear la reserva");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="catalog">
      <SearchBar onSearch={handleSearch} loading={loading} />
      {error && <p className="error">{error}</p>}
      <div className="catalog-layout">
        <BookResults books={results} selectedIsbn={selectedBook?.isbn} onSelect={handleSelect} />
        <div className="catalog-detail">
          {confirmationMessage && <p className="success">{confirmationMessage}</p>}
          {availability && <BookAvailabilityView availability={availability} onReserve={setReservingPhysicalBookId} />}
          {reservingPhysicalBookId !== null && (
            <ReservationForm
              physicalBookId={reservingPhysicalBookId}
              submitting={submitting}
              onCancel={() => setReservingPhysicalBookId(null)}
              onSubmit={handleReserve}
            />
          )}
        </div>
      </div>
    </div>
  );
}
