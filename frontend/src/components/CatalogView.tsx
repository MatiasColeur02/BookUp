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
import { ErrorBanner } from "./ErrorBanner";
import { Modal } from "./Modal";

const PAGE_SIZE = 12;

export function CatalogView() {
  const { user } = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  // El libro elegido y la reserva en curso viven en la URL: así el flujo sobrevive al
  // rodeo por `/login` y la ficha queda compartible.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedIsbn = searchParams.get("isbn");
  const reservingId = Number(searchParams.get("reservar")) || null;

  // El catálogo que se muestra al entrar, sin buscar nada: una página de `GET /books`
  // que se va extendiendo con "Cargar más".
  const [catalog, setCatalog] = useState<Book[]>([]);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  // `null` = no hay búsqueda activa, se muestra el catálogo.
  const [searchResults, setSearchResults] = useState<Book[] | null>(null);
  const [activeQuery, setActiveQuery] = useState("");
  const [availability, setAvailability] = useState<BookAvailability | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingAvailability, setLoadingAvailability] = useState(false);
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
    setLoadingAvailability(true);
    api.books
      .availability(selectedIsbn)
      .then((next) => {
        if (!cancelled) setAvailability(next);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingAvailability(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedIsbn]);

  // Primera página del catálogo al entrar: la pantalla arranca con libros, no vacía.
  useEffect(() => {
    let cancelled = false;
    api.books
      .list({ limit: PAGE_SIZE, offset: 0 })
      .then((page) => {
        if (cancelled) return;
        setCatalog(page.items);
        setCatalogTotal(page.total);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingCatalog(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoadMore = async () => {
    setLoadingMore(true);
    setError(null);
    try {
      const page = await api.books.list({ limit: PAGE_SIZE, offset: catalog.length });
      setCatalog((current) => [...current, ...page.items]);
      setCatalogTotal(page.total);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSearch = async (query: string) => {
    setLoading(true);
    setError(null);
    setConfirmationMessage(null);
    try {
      setSearchResults(await api.books.search(query));
      setActiveQuery(query);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  };

  // Limpiar la búsqueda devuelve el catálogo ya cargado, sin volver a pedirlo.
  const handleClearSearch = () => {
    setSearchResults(null);
    setActiveQuery("");
    setError(null);
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

  const closeDetail = () => {
    setSearchParams({});
    setError(null);
    setConfirmationMessage(null);
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

  const searching = searchResults !== null;
  const shownBooks = searchResults ?? catalog;
  const canLoadMore = !searching && catalog.length < catalogTotal;
  const listCaption = searching
    ? `${shownBooks.length} ${shownBooks.length === 1 ? "resultado" : "resultados"} para «${activeQuery}»`
    : `${catalog.length} de ${catalogTotal}`;

  const selectedBook = shownBooks.find((book) => book.isbn === selectedIsbn) ?? null;

  const reservingOption =
    reservingId === null
      ? null
      : availability?.libraries.find((option) => option.physical_book_id === reservingId) ?? null;

  return (
    <div className="catalog">
      <SearchBar onSearch={handleSearch} onClear={handleClearSearch} loading={loading} />
      {/* Con el modal abierto el error se muestra adentro, no tapado detrás del fondo. */}
      <ErrorBanner error={selectedIsbn === null ? error : null} />
      <div className="catalog-layout">
        <div className="catalog-results">
          <div className="catalog-results-header">
            <h2>{searching ? "Resultados" : "Catálogo"}</h2>
            <span className="muted">{listCaption}</span>
          </div>
          {loadingCatalog && !searching ? (
            <p className="muted">Cargando catálogo...</p>
          ) : (
            <>
              <BookResults
                books={shownBooks}
                selectedIsbn={selectedIsbn ?? undefined}
                onSelect={handleSelect}
                emptyMessage={
                  searching
                    ? `No encontramos libros para «${activeQuery}». Probá con otro título, autor o ISBN.`
                    : "Todavía no hay libros en el catálogo."
                }
              />
              {canLoadMore && (
                <button className="load-more" onClick={handleLoadMore} disabled={loadingMore}>
                  {loadingMore ? "Cargando..." : "Cargar más"}
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* La ficha del libro es un modal: el título sale de la disponibilidad ya
          cargada, y mientras viaja se usa el que veníamos mostrando en la grilla. */}
      {selectedIsbn !== null && (
        <Modal
          title={availability?.book.title ?? selectedBook?.title ?? "Ficha del libro"}
          onClose={closeDetail}
        >
          <div className="catalog-detail">
            {confirmationMessage && <p className="success">{confirmationMessage}</p>}
            <ErrorBanner error={error} />
            {loadingAvailability && <p className="muted">Consultando disponibilidad...</p>}
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
        </Modal>
      )}
    </div>
  );
}
