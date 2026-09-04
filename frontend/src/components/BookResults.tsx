import type { Book } from "../types";

interface Props {
  books: Book[];
  selectedId?: number;
  onSelect: (book: Book) => void;
}

export function BookResults({ books, selectedId, onSelect }: Props) {
  if (books.length === 0) {
    return <p className="empty">Buscá un título, autor o ISBN para ver resultados.</p>;
  }

  return (
    <ul className="book-list">
      {books.map((book) => (
        <li key={book.id} className={book.id === selectedId ? "selected" : ""}>
          <button onClick={() => onSelect(book)}>
            <strong>{book.title}</strong>
            <span>{book.author}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
