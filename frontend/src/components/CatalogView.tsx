import { useState } from "react";
import { api } from "../api";
import type { Book, BookAvailability } from "../types";
import { BookAvailabilityView } from "./BookAvailabilityView";
import { BookResults } from "./BookResults";
import { ReservationForm } from "./ReservationForm";
import { SearchBar } from "./SearchBar";

export function CatalogView() {
  const [results, setResults] = useState<Book[]>([]);
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [availability, setAvailability] = useState<BookAvailability | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reservingCopyId, setReservingCopyId] = useState<number | null>(null);
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
    setReservingCopyId(null);
    setConfirmationMessage(null);
    try {
      setAvailability(await api.getAvailability(book.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al consultar disponibilidad");
    }
  };

  const handleReserve = async (data: { patron_name: string; patron_email: string }) => {
    if (reservingCopyId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createReservation({ copy_id: reservingCopyId, ...data });
      setConfirmationMessage("Reserva creada. Retirala en la biblioteca seleccionada.");
      setReservingCopyId(null);
      if (selectedBook) {
        setAvailability(await api.getAvailability(selectedBook.id));
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
        <BookResults books={results} selectedId={selectedBook?.id} onSelect={handleSelect} />
        <div className="catalog-detail">
          {confirmationMessage && <p className="success">{confirmationMessage}</p>}
          {availability && <BookAvailabilityView availability={availability} onReserve={setReservingCopyId} />}
          {reservingCopyId !== null && (
            <ReservationForm
              copyId={reservingCopyId}
              submitting={submitting}
              onCancel={() => setReservingCopyId(null)}
              onSubmit={handleReserve}
            />
          )}
        </div>
      </div>
    </div>
  );
}
