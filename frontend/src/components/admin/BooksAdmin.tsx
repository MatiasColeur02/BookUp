import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { describeError } from "../../lib/errors";
import type { Author, Book, Genre } from "../../types";
import { BookForm } from "./BookForm";
import { ErrorBanner } from "../ErrorBanner";

type FormState = { mode: "hidden" } | { mode: "create" } | { mode: "edit"; book: Book };

export function BooksAdmin() {
  const [books, setBooks] = useState<Book[]>([]);
  const [authors, setAuthors] = useState<Author[]>([]);
  const [genres, setGenres] = useState<Genre[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({ mode: "hidden" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // `GET /books` es el listado completo del catálogo, distinto de `/books/search`.
      const [nextBooks, nextAuthors, nextGenres] = await Promise.all([
        api.books.list(),
        api.authors.list(),
        api.genres.list(),
      ]);
      setBooks(nextBooks);
      setAuthors(nextAuthors);
      setGenres(nextGenres);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSaved = async () => {
    setForm({ mode: "hidden" });
    await load();
  };

  const handleRemove = async (book: Book) => {
    if (!window.confirm(`¿Eliminar «${book.title}» del catálogo?`)) return;
    setError(null);
    try {
      await api.books.remove(book.isbn);
      await load();
    } catch (err) {
      setError(
        describeError(err, {
          409: "No se puede eliminar: el libro todavía tiene ejemplares en alguna sede. Dalos de baja desde «Ejemplares» primero.",
        })
      );
    }
  };

  return (
    <section className="librarian-panel">
      <div className="panel-filters">
        <h2>Libros</h2>
        {form.mode === "hidden" && (
          <button className="confirm-button" onClick={() => setForm({ mode: "create" })}>
            Nuevo libro
          </button>
        )}
      </div>

      <ErrorBanner error={error} />

      {form.mode !== "hidden" && (
        <BookForm
          key={form.mode === "edit" ? form.book.isbn : "nuevo"}
          book={form.mode === "edit" ? form.book : undefined}
          authors={authors}
          genres={genres}
          onSaved={handleSaved}
          onCancel={() => setForm({ mode: "hidden" })}
        />
      )}

      {loading ? (
        <p className="muted">Cargando catálogo...</p>
      ) : books.length === 0 ? (
        <p className="empty">
          El catálogo está vacío. Cargá <Link to="/gestion/autores">autores</Link> y{" "}
          <Link to="/gestion/generos">géneros</Link> antes de dar de alta un libro.
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ISBN</th>
                <th>Título</th>
                <th>Autores</th>
                <th>Géneros</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {books.map((book) => (
                <tr key={book.isbn}>
                  <td>
                    <span className="badge">{book.isbn}</span>
                  </td>
                  <td>{book.title}</td>
                  <td>{book.authors.map((author) => author.name).join(", ") || "—"}</td>
                  <td>{book.genres.map((genre) => genre.name).join(", ") || "—"}</td>
                  <td>
                    <div className="row-actions">
                      <button className="row-button" onClick={() => setForm({ mode: "edit", book })}>
                        Editar
                      </button>
                      <button className="row-button danger" onClick={() => handleRemove(book)}>
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
