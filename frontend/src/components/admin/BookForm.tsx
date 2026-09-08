import { useState, type FormEvent } from "react";
import { api } from "../../api";
import { describeError } from "../../lib/errors";
import { isValidIsbn13 } from "../../lib/isbn";
import type { Author, Book, Genre } from "../../types";

interface Props {
  /** `undefined` = alta; con un libro = edición (el ISBN es la PK y no se toca). */
  book?: Book;
  authors: Author[];
  genres: Genre[];
  onSaved: () => void;
  onCancel: () => void;
}

/** Ids seleccionados en un `<select multiple>`. */
function selectedIds(select: HTMLSelectElement): number[] {
  return Array.from(select.selectedOptions, (option) => Number(option.value));
}

export function BookForm({ book, authors, genres, onSaved, onCancel }: Props) {
  const editing = book !== undefined;

  const [isbn, setIsbn] = useState(book?.isbn ?? "");
  const [title, setTitle] = useState(book?.title ?? "");
  const [language, setLanguage] = useState(book?.language ?? "es");
  const [pages, setPages] = useState(book?.pages?.toString() ?? "");
  const [synopsis, setSynopsis] = useState(book?.synopsis ?? "");
  // Precargados con la selección actual: mandar estas listas en un PATCH **reemplaza**
  // la lista completa, así que arrancar vacío borraría autores y géneros sin querer.
  const [authorIds, setAuthorIds] = useState<number[]>(book?.authors.map((a) => a.id) ?? []);
  const [genreIds, setGenreIds] = useState<number[]>(book?.genres.map((g) => g.id) ?? []);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (!editing && !isValidIsbn13(isbn)) {
      setError("El ISBN tiene que ser un ISBN-13 válido: 13 dígitos con dígito verificador correcto.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const fields = {
        title,
        language,
        pages: pages === "" ? null : Number(pages),
        synopsis: synopsis === "" ? null : synopsis,
        author_ids: authorIds,
        genre_ids: genreIds,
      };

      if (editing) {
        await api.books.update(book.isbn, fields);
      } else {
        await api.books.create({ isbn, ...fields });
      }
      onSaved();
    } catch (err) {
      setError(
        describeError(err, {
          409: "Ya existe un libro con ese ISBN.",
          404: "Alguno de los autores o géneros elegidos ya no existe. Recargá la página.",
        })
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="form-card" onSubmit={handleSubmit}>
      <h3>{editing ? `Editar «${book.title}»` : "Nuevo libro"}</h3>

      {error && <p className="error">{error}</p>}

      <label>
        ISBN
        <input
          value={isbn}
          onChange={(event) => setIsbn(event.target.value)}
          disabled={editing}
          inputMode="numeric"
          maxLength={13}
          required
        />
        <span className="field-hint">
          {editing ? "El ISBN identifica al libro y no se puede cambiar." : "13 dígitos, sin guiones."}
        </span>
      </label>

      <label>
        Título
        <input value={title} onChange={(event) => setTitle(event.target.value)} required />
      </label>

      <label>
        Idioma
        <input value={language} onChange={(event) => setLanguage(event.target.value)} required />
      </label>

      <label>
        Páginas
        <input
          type="number"
          min={1}
          value={pages}
          onChange={(event) => setPages(event.target.value)}
          placeholder="Opcional"
        />
      </label>

      <label>
        Sinopsis
        <textarea
          rows={4}
          value={synopsis}
          onChange={(event) => setSynopsis(event.target.value)}
          placeholder="Opcional"
        />
      </label>

      <label>
        Autores
        <select
          multiple
          size={5}
          value={authorIds.map(String)}
          onChange={(event) => setAuthorIds(selectedIds(event.target))}
        >
          {authors.map((author) => (
            <option key={author.id} value={author.id}>
              {author.name} (#{author.id})
            </option>
          ))}
        </select>
        <span className="field-hint">Ctrl/Cmd + clic para elegir varios.</span>
      </label>

      <label>
        Géneros
        <select
          multiple
          size={5}
          value={genreIds.map(String)}
          onChange={(event) => setGenreIds(selectedIds(event.target))}
        >
          {genres.map((genre) => (
            <option key={genre.id} value={genre.id}>
              {genre.name}
            </option>
          ))}
        </select>
      </label>

      <div className="actions">
        <button type="button" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" disabled={submitting}>
          {submitting ? "Guardando..." : editing ? "Guardar cambios" : "Crear libro"}
        </button>
      </div>
    </form>
  );
}
