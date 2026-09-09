import type { Book } from "../types";
import { BookCover } from "./BookCover";
import { BookIcon } from "./icons";

interface Props {
  books: Book[];
  selectedIsbn?: string;
  onSelect: (book: Book) => void;
  /** Qué decir cuando no hay nada que listar; depende de si veníamos de una búsqueda. */
  emptyMessage?: string;
}

export function BookResults({ books, selectedIsbn, onSelect, emptyMessage }: Props) {
  if (books.length === 0) {
    return (
      <div className="empty-state">
        <BookIcon className="empty-state-icon" />
        <p>{emptyMessage ?? "Buscá un título, autor o ISBN para ver resultados."}</p>
      </div>
    );
  }

  return (
    <ul className="book-grid">
      {books.map((book) => (
        <li key={book.isbn} className={book.isbn === selectedIsbn ? "selected" : ""}>
          <button onClick={() => onSelect(book)}>
            <span className="book-cover-frame">
              <BookCover book={book} />
              <span className="book-cover-hint" aria-hidden="true">
                Ver disponibilidad
              </span>
            </span>
            <strong>{book.title}</strong>
            <span>{book.authors.map((author) => author.name).join(", ") || "Autor desconocido"}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Placeholder de carga con la forma final de la grilla: evita el salto al llegar los datos. */
export function BookResultsSkeleton({ count = 12 }: { count?: number }) {
  return (
    <ul className="book-grid-skeleton" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <li key={index}>
          <div className="skeleton skeleton-cover" />
          <div className="skeleton skeleton-line" style={{ width: "80%" }} />
          <div className="skeleton skeleton-line" style={{ width: "55%" }} />
        </li>
      ))}
    </ul>
  );
}
