import { useCallback, useEffect, useRef, useState } from "react";
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
import { Pagination } from "./Pagination";
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
  // La página también: así «atrás» vuelve a la página anterior en vez de salir del
  // catálogo, y cerrar la ficha de un libro no te deja de nuevo en la primera.
  const page = Math.max(1, Number(searchParams.get("page")) || 1);

  /**
   * Reescribe los params conservando la página. Todo lo que toca la URL pasa por acá:
   * un `setSearchParams({ isbn })` suelto borraría el `page` sin querer.
   */
  const setParams = useCallback(
    (next: { isbn?: string; reservar?: number; page?: number }) => {
      const params: Record<string, string> = {};
      const nextPage = next.page ?? page;
      if (nextPage > 1) params.page = String(nextPage);
      if (next.isbn) params.isbn = next.isbn;
      if (next.reservar) params.reservar = String(next.reservar);
      setSearchParams(params);
    },
    [page, setSearchParams]
  );

  // Buscar y filtrar son la misma consulta: `GET /books` acepta texto y filtros juntos
  // y devuelve una página. Por eso hay una sola lista, no una de catálogo y otra de
  // resultados.
  const [books, setBooks] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  // `queryInput` es lo tipeado; `activeQuery` es lo que se está filtrando. Se separan
  // porque la búsqueda se dispara al enviar, no en cada tecla.
  const [queryInput, setQueryInput] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [filters, setFilters] = useState<CatalogFilterState>(EMPTY_FILTERS);
  const filterOptions = useCatalogFilterOptions();
  const resultsRef = useRef<HTMLDivElement>(null);
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

  // Una página a la vez: cambia al entrar, al cambiar el texto o un filtro, y al
  // cambiar de página.
  useEffect(() => {
    let cancelled = false;
    setLoadingCatalog(true);
    setError(null);
    api.books
      .list({ ...buildQuery(), limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
      .then((result) => {
        if (cancelled) return;
        setBooks(result.items);
        setTotal(result.total);
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
  }, [buildQuery, page]);

  const handlePageChange = (next: number) => {
    setParams({ page: next });
    // Los controles están arriba y abajo: si se cambió desde los de abajo, hay que
    // volver al principio de la lista o la página nueva arranca a mitad de scroll.
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Buscar y filtrar vuelven a la página 1: la 4 de un resultado no existe en el otro.
  const handleSearch = (query: string) => {
    setActiveQuery(query);
    setParams({ page: 1 });
  };

  const handleClearSearch = () => {
    setQueryInput("");
    setActiveQuery("");
    setParams({ page: 1 });
  };

  const handleFiltersChange = (next: CatalogFilterState) => {
    setFilters(next);
    setParams({ page: 1 });
  };

  const handleSelect = (book: Book) => {
    setError(null);
    setParams({ isbn: book.isbn });
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

    setParams({ isbn: selectedIsbn, reservar: physicalBookId });
  };

  const closeDetail = () => {
    setParams({});
    setError(null);
  };

  const closeReservationForm = () => {
    if (selectedIsbn !== null) setParams({ isbn: selectedIsbn });
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
      setParams({ isbn: selectedIsbn });
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
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const listCaption = filtering
    ? `${total} ${total === 1 ? "resultado" : "resultados"}`
    : `${total} ${total === 1 ? "libro" : "libros"}`;

  // Si un filtro dejó menos páginas que la que estabas mirando, la URL apunta a una
  // página vacía: se la corrige sola en vez de mostrar la grilla en blanco.
  useEffect(() => {
    if (!loadingCatalog && page > totalPages) setParams({ page: totalPages });
  }, [loadingCatalog, page, totalPages, setParams]);

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
        <CatalogFilters filters={filters} options={filterOptions} onChange={handleFiltersChange} />
      </div>
      {/* Con el modal abierto el error se muestra adentro, no tapado detrás del fondo. */}
      <ErrorBanner error={selectedIsbn === null ? error : null} />
      <div className="catalog-results" ref={resultsRef}>
        <div className="catalog-results-header">
          <h2>{filtering ? "Resultados" : "Catálogo"}</h2>
          <span className="badge badge-neutral">{listCaption}</span>
          <ActiveFilters
            query={activeQuery}
            filters={filters}
            options={filterOptions}
            onRemoveQuery={handleClearSearch}
            onChange={handleFiltersChange}
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
            <Pagination page={page} totalPages={totalPages} onChange={handlePageChange} />
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
            {/* Reservar **reemplaza** la ficha, no se agrega abajo: con muchas sedes
                disponibles el formulario quedaba fuera de la pantalla y no se veía el
                botón de confirmar. La flecha vuelve a la lista de sedes. */}
            {reservingOption ? (
              <ReservationForm
                option={reservingOption}
                bookTitle={availability?.book.title ?? selectedBook?.title ?? "este libro"}
                submitting={submitting}
                onBack={closeReservationForm}
                onCancel={closeDetail}
                onSubmit={handleReserve}
              />
            ) : (
              availability && (
                <BookAvailabilityView
                  availability={availability}
                  onReserve={handleStartReservation}
                />
              )
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
