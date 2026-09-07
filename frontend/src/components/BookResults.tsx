import type { Book } from "../types";
import { BookIcon } from "./icons";

interface Props {
  books: Book[];
  selectedIsbn?: string;
  onSelect: (book: Book) => void;
}

export function BookResults({ books, selectedIsbn, onSelect }: Props) {
  if (books.length === 0) {
    return (
      <div className="empty-state">
        <BookIcon className="empty-state-icon" />
        <p>Buscá un título, autor o ISBN para ver resultados.</p>
      </div>
    );
  }

  return (
    <ul className="book-list">
      {books.map((book) => (
        <li key={book.isbn} className={book.isbn === selectedIsbn ? "selected" : ""}>
          <button onClick={() => onSelect(book)}>
            <strong>{book.title}</strong>
            <span>{book.authors.map((author) => author.name).join(", ") || "Autor desconocido"}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
