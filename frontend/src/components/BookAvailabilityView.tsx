import type { BookAvailability } from "../types";
import { BookCover } from "./BookCover";
import { PinIcon } from "./icons";

interface Props {
  availability: BookAvailability;
  onReserve: (physicalBookId: number) => void;
}

export function BookAvailabilityView({ availability, onReserve }: Props) {
  const { book, libraries } = availability;

  return (
    <div className="availability">
      <span className="eyebrow">Ficha del libro</span>
      <div className="availability-header">
        <div className="availability-cover">
          <BookCover book={book} loading="eager" />
        </div>
        <div>
          <h2>{book.title}</h2>
          <p className="author">
            {book.authors.map((author) => author.name).join(", ") || "Autor desconocido"}
          </p>
          {book.genres.length > 0 && (
            <ul className="book-genres">
              {book.genres.map((genre) => (
                <li key={genre.id}>
                  <span className="badge">{genre.name}</span>
                </li>
              ))}
            </ul>
          )}
          {/* Metadatos terciarios: en una línea al pie, no como párrafos sueltos. */}
          <p className="book-meta">
            <span className="badge badge-neutral">ISBN {book.isbn}</span>
            <span>{book.language.toUpperCase()}</span>
            {book.pages !== null && <span>· {book.pages} páginas</span>}
          </p>
        </div>
      </div>

      {book.synopsis && <p className="synopsis">{book.synopsis}</p>}

      <h3>Disponibilidad por biblioteca</h3>
      {libraries.length === 0 ? (
        <p className="callout">No hay ejemplares disponibles en ninguna sede en este momento.</p>
      ) : (
        <ul className="library-list">
          {libraries.map(({ library, available_copies, physical_book_id }) => (
            <li key={library.id}>
              <div>
                <strong>{library.name}</strong>
                <span>
                  <PinIcon className="inline-icon" />
                  {library.city}
                  <span className="badge badge-success">
                    {available_copies} disponible{available_copies === 1 ? "" : "s"}
                  </span>
                </span>
              </div>
              <button className="btn btn-primary btn-sm" onClick={() => onReserve(physical_book_id)}>
                Reservar
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
