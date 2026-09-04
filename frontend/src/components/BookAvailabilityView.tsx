import type { BookAvailability } from "../types";

interface Props {
  availability: BookAvailability;
  onReserve: (copyId: number) => void;
}

export function BookAvailabilityView({ availability, onReserve }: Props) {
  const { book, libraries } = availability;

  return (
    <div className="availability">
      <h2>{book.title}</h2>
      <p className="author">{book.author}</p>
      {book.synopsis && <p className="synopsis">{book.synopsis}</p>}
      <p className="isbn">ISBN: {book.isbn}</p>

      <h3>Disponibilidad por biblioteca</h3>
      {libraries.length === 0 ? (
        <p className="empty">No hay ejemplares disponibles en ninguna sede en este momento.</p>
      ) : (
        <ul className="library-list">
          {libraries.map(({ library, available_copies, copy_id }) => (
            <li key={library.id}>
              <div>
                <strong>{library.name}</strong>
                <span>
                  {library.city} · {available_copies} disponible{available_copies === 1 ? "" : "s"}
                </span>
              </div>
              <button onClick={() => onReserve(copy_id)}>Reservar</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
