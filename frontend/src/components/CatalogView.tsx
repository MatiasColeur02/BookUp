import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../context/SessionContext";
import { useToast } from "../context/ToastContext";
import { describeError } from "../lib/errors";
import type { Book, BookAvailability } from "../types";
import { BookAvailabilityView } from "./BookAvailabilityView";
import { BookResults, BookResultsSkeleton } from "./BookResults";
import {
  CatalogFilters,
  countFilters,
  EMPTY_FILTERS,
  type CatalogFilterState,
} from "./CatalogFilters";
import { ActiveFilters } from "./ActiveFilters";
import { useCatalogFilterOptions } from "../hooks/useCatalogFilterOptions";
import { ReservationForm } from "./ReservationForm";
import { SearchBar } from "./SearchBar";
import { ErrorBanner } from "./ErrorBanner";
import { Modal } from "./Modal";

const PAGE_SIZE = 12;

export function CatalogView() {
  const { user } = useSession();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  // El libro elegido y la reserva en curso viven en la URL: así el flujo sobrevive al
  // rodeo por `/login` y la ficha queda compartible.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedIsbn = searchParams.get("isbn");
  const reservingId = Number(searchParams.get("reservar")) || null;

  // Buscar y filtrar son la misma consulta: `GET /books` acepta texto y filtros juntos
  // y devuelve una página. Por eso hay una sola lista, no una de catálogo y otra de
  // resultados.
  const [books, setBooks] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  // `queryInput` es lo tipeado; `activeQuery` es lo que se está filtrando. Se separan
  // porque la búsqueda se dispara al enviar, no en cada tecla.
  const [queryInput, setQueryInput] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [filters, setFilters] = useState<CatalogFilterState>(EMPTY_FILTERS);
  const filterOptions = useCatalogFilterOptions();
  const [availability, setAvailability] = useState<BookAvailability | null>(
    null,
  );
  const [loadingAvailability, setLoadingAvailability] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  /** Los parámetros de `GET /books` que salen del estado actual de la pantalla. */
  const buildQuery = useCallback(
    () => ({
      q: activeQuery === "" ? undefined : activeQuery,
      author_id: filters.authorIds,
      genre_id: filters.genreIds,
      city: filters.cities,
    }),
    [activeQuery, filters]
  );

  // Primera página: al entrar, y de nuevo cada vez que cambia el texto o un filtro.
  useEffect(() => {
    let cancelled = false;
    setLoadingCatalog(true);
    setError(null);
    api.books
      .list({ ...buildQuery(), limit: PAGE_SIZE, offset: 0 })
      .then((page) => {
        if (cancelled) return;
        setBooks(page.items);
        setTotal(page.total);
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
  }, [buildQuery]);

  const handleLoadMore = async () => {
    setLoadingMore(true);
    setError(null);
    try {
      // El offset sale de lo que ya está en pantalla, con los mismos filtros.
      const page = await api.books.list({ ...buildQuery(), limit: PAGE_SIZE, offset: books.length });
      setBooks((current) => [...current, ...page.items]);
      setTotal(page.total);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoadingMore(false);
    }
  };

  // Buscar y limpiar solo tocan el estado: la consulta la dispara el efecto de arriba.
  const handleSearch = (query: string) => setActiveQuery(query);

  const handleClearSearch = () => {
    setQueryInput("");
    setActiveQuery("");
  };

  const handleSelect = (book: Book) => {
    setError(null);
    setSearchParams({ isbn: book.isbn });
  };

  const handleStartReservation = (physicalBookId: number) => {
    if (selectedIsbn === null) return;
    const search = `?isbn=${encodeURIComponent(selectedIsbn)}&reservar=${physicalBookId}`;

    if (!user) {
      // Sin sesión no se puede reservar: el dueño sale del token. Guardamos el ejemplar
      // elegido en la URL de vuelta para retomar la reserva después del login.
      navigate("/login", {
        state: { from: { pathname: location.pathname, search } },
      });
      return;
    }

    setSearchParams({ isbn: selectedIsbn, reservar: String(physicalBookId) });
  };

  const closeDetail = () => {
    setSearchParams({});
    setError(null);
  };

  const closeReservationForm = () => {
    if (selectedIsbn !== null) setSearchParams({ isbn: selectedIsbn });
  };

  const handleReserve = async (expiresAt: string) => {
    if (reservingId === null || selectedIsbn === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.reservations.create({
        physical_book_id: reservingId,
        expires_at: expiresAt,
      });
      toast.success("Reserva creada. Podés seguirla desde «Mis reservas».");
      setSearchParams({ isbn: selectedIsbn });
      // El ejemplar pasó a `reserved`: la disponibilidad que se está mostrando quedó vieja.
      await loadAvailability(selectedIsbn);
    } catch (err) {
      toast.error(err, {
        409: "Alguien reservó este ejemplar antes que vos. Probá con otra sede.",
      });
      // Puede haber cambiado la disponibilidad entre la consulta y el alta.
      await loadAvailability(selectedIsbn).catch(() => undefined);
    } finally {
      setSubmitting(false);
    }
  };

  const filtering = activeQuery !== "" || countFilters(filters) > 0;
  const canLoadMore = books.length < total;
  const listCaption = filtering
    ? `${total} ${total === 1 ? "resultado" : "resultados"}`
    : `${books.length} de ${total}`;

  const selectedBook = books.find((book) => book.isbn === selectedIsbn) ?? null;

  const reservingOption =
    reservingId === null
      ? null
      : (availability?.libraries.find(
          (option) => option.physical_book_id === reservingId,
        ) ?? null);

  return (
    <div className="catalog">
      <div className="catalog-search">
        <SearchBar
          value={queryInput}
          onValueChange={setQueryInput}
          onSearch={handleSearch}
          onClear={handleClearSearch}
          loading={loadingCatalog}
        />
        {!filtering && total > 0 && (
          <p className="search-hint">
            Buscá entre {total} libros de toda la red por título, autor, ISBN o sinopsis.
          </p>
        )}
        <CatalogFilters filters={filters} options={filterOptions} onChange={setFilters} />
      </div>
      {/* Con el modal abierto el error se muestra adentro, no tapado detrás del fondo. */}
      <ErrorBanner error={selectedIsbn === null ? error : null} />
      <div className="catalog-results">
        <div className="catalog-results-header">
          <h2>{filtering ? "Resultados" : "Catálogo"}</h2>
          <span className="badge badge-neutral">{listCaption}</span>
          <ActiveFilters
            query={activeQuery}
            filters={filters}
            options={filterOptions}
            onRemoveQuery={handleClearSearch}
            onChange={setFilters}
          />
        </div>
        {loadingCatalog ? (
          <BookResultsSkeleton />
        ) : (
          <>
            <BookResults
              books={books}
              selectedIsbn={selectedIsbn ?? undefined}
              onSelect={handleSelect}
              emptyMessage={
                filtering
                  ? "Ningún libro coincide con lo que buscás. Probá quitando algún filtro."
                  : "Todavía no hay libros en el catálogo."
              }
            />
            {canLoadMore && (
              <div className="load-more-wrap">
                <button
                  className="btn btn-secondary"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                >
                  {loadingMore
                    ? "Cargando..."
                    : `Cargar más — ${total - books.length} restantes`}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* La ficha del libro es un modal: el título sale de la disponibilidad ya
          cargada, y mientras viaja se usa el que veníamos mostrando en la grilla. */}
      {selectedIsbn !== null && (
        <Modal
          title={
            availability?.book.title ?? selectedBook?.title ?? "Ficha del libro"
          }
          onClose={closeDetail}
        >
          <div className="card catalog-detail">
            {/* Los errores de acción salen por toast; acá solo si la ficha no cargó. */}
            <ErrorBanner error={error} />
            {loadingAvailability && (
              <p className="muted">Consultando disponibilidad...</p>
            )}
            {availability && (
              <BookAvailabilityView
                availability={availability}
                onReserve={handleStartReservation}
              />
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
