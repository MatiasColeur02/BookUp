import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import { describeError } from "../lib/errors";
import type { Book, BookAvailability } from "../types";
import { BookAvailabilityView } from "./BookAvailabilityView";
import { BookResults } from "./BookResults";
import { ReservationForm } from "./ReservationForm";
import { SearchBar } from "./SearchBar";

export function CatalogView() {
  const { user } = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  // El libro elegido y la reserva en curso viven en la URL: así el flujo sobrevive al
  // rodeo por `/login` y la ficha queda compartible.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedIsbn = searchParams.get("isbn");
  const reservingId = Number(searchParams.get("reservar")) || null;

  const [results, setResults] = useState<Book[]>([]);
  const [availability, setAvailability] = useState<BookAvailability | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmationMessage, setConfirmationMessage] = useState<string | null>(null);

  const loadAvailability = useCallback(async (isbn: string) => {
    setAvailability(await api.books.availability(isbn));
  }, []);

  useEffect(() => {
    if (selectedIsbn === null) {
      setAvailability(null);
      return;
    }
    let cancelled = false;
    api.books
      .availability(selectedIsbn)
      .then((next) => {
        if (!cancelled) setAvailability(next);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [selectedIsbn]);

  const handleSearch = async (query: string) => {
    setLoading(true);
    setError(null);
    setConfirmationMessage(null);
    try {
      setResults(await api.books.search(query));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (book: Book) => {
    setError(null);
    setConfirmationMessage(null);
    setSearchParams({ isbn: book.isbn });
  };

  const handleStartReservation = (physicalBookId: number) => {
    if (selectedIsbn === null) return;
    const search = `?isbn=${encodeURIComponent(selectedIsbn)}&reservar=${physicalBookId}`;

    if (!user) {
      // Sin sesión no se puede reservar: el dueño sale del token. Guardamos el ejemplar
      // elegido en la URL de vuelta para retomar la reserva después del login.
      navigate("/login", { state: { from: { pathname: location.pathname, search } } });
      return;
    }

    setConfirmationMessage(null);
    setSearchParams({ isbn: selectedIsbn, reservar: String(physicalBookId) });
  };

  const closeReservationForm = () => {
    if (selectedIsbn !== null) setSearchParams({ isbn: selectedIsbn });
  };

  const handleReserve = async (expiresAt: string) => {
    if (reservingId === null || selectedIsbn === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.reservations.create({ physical_book_id: reservingId, expires_at: expiresAt });
      setConfirmationMessage("Reserva creada. Podés seguirla desde «Mis reservas».");
      setSearchParams({ isbn: selectedIsbn });
      // El ejemplar pasó a `reserved`: la disponibilidad que se está mostrando quedó vieja.
      await loadAvailability(selectedIsbn);
    } catch (err) {
      setError(
        describeError(err, {
          409: "Alguien reservó este ejemplar antes que vos. Probá con otra sede.",
        })
      );
      // Puede haber cambiado la disponibilidad entre la consulta y el alta.
      await loadAvailability(selectedIsbn).catch(() => undefined);
    } finally {
      setSubmitting(false);
    }
  };

  const reservingOption =
    reservingId === null
      ? null
      : availability?.libraries.find((option) => option.physical_book_id === reservingId) ?? null;

  return (
    <div className="catalog">
      <SearchBar onSearch={handleSearch} loading={loading} />
      {error && <p className="error">{error}</p>}
      <div className="catalog-layout">
        <BookResults books={results} selectedIsbn={selectedIsbn ?? undefined} onSelect={handleSelect} />
        <div className="catalog-detail">
          {confirmationMessage && <p className="success">{confirmationMessage}</p>}
          {availability && (
            <BookAvailabilityView availability={availability} onReserve={handleStartReservation} />
          )}
          {reservingOption && (
            <ReservationForm
              option={reservingOption}
              submitting={submitting}
              onCancel={closeReservationForm}
              onSubmit={handleReserve}
            />
          )}
        </div>
      </div>
    </div>
  );
}
