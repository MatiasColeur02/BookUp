import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import { describeError } from "../../lib/errors";
import type { Author, Book, Genre } from "../../types";
import { BookForm } from "./BookForm";
import { ErrorBanner } from "../ErrorBanner";
import { Modal } from "../Modal";
import { TableSkeleton } from "../Skeleton";

type FormState = { mode: "hidden" } | { mode: "create" } | { mode: "edit"; book: Book };

export function BooksAdmin() {
  const confirm = useConfirm();
  const toast = useToast();
  const [books, setBooks] = useState<Book[]>([]);
  const [authors, setAuthors] = useState<Author[]>([]);
  const [genres, setGenres] = useState<Genre[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({ mode: "hidden" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // `GET /books` es el catálogo entero (paginado), distinto de `/books/search`.
      const [nextBooks, nextAuthors, nextGenres] = await Promise.all([
        api.books.listAll(),
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
    const confirmed = await confirm({
      tone: "danger",
      title: "Eliminar del catálogo",
      message:
        "El libro sale del catálogo de toda la red. Si tiene ejemplares en alguna sede, la API lo va a rechazar.",
      details: [
        { label: "Libro", value: book.title },
        { label: "ISBN", value: book.isbn },
      ],
      confirmLabel: "Eliminar libro",
    });
    if (!confirmed) return;
    setError(null);
    try {
      await api.books.remove(book.isbn);
      toast.success(`«${book.title}» se eliminó del catálogo.`);
      await load();
    } catch (err) {
      toast.error(err, {
        409: "No se puede eliminar: el libro todavía tiene ejemplares en alguna sede. Dalos de baja desde «Ejemplares» primero.",
      });
    }
  };

  return (
    <section className="stack">
      <div className="page-header">
        <h2>Libros</h2>
        <button className="btn btn-primary" onClick={() => setForm({ mode: "create" })}>
          Nuevo libro
        </button>
      </div>

      <ErrorBanner error={error} />

      {form.mode !== "hidden" && (
        <Modal
          title={form.mode === "edit" ? `Editar «${form.book.title}»` : "Nuevo libro"}
          onClose={() => setForm({ mode: "hidden" })}
        >
          <BookForm
            key={form.mode === "edit" ? form.book.isbn : "nuevo"}
            book={form.mode === "edit" ? form.book : undefined}
            authors={authors}
            genres={genres}
            onSaved={handleSaved}
            onCancel={() => setForm({ mode: "hidden" })}
          />
        </Modal>
      )}

      {loading ? (
        <TableSkeleton />
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
                    <span className="badge badge-neutral">{book.isbn}</span>
                  </td>
                  <td>{book.title}</td>
                  <td>{book.authors.map((author) => author.name).join(", ") || "—"}</td>
                  <td>{book.genres.map((genre) => genre.name).join(", ") || "—"}</td>
                  <td>
                    <div className="row-actions">
                      <button className="btn btn-secondary btn-sm" onClick={() => setForm({ mode: "edit", book })}>
                        Editar
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleRemove(book)}>
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
