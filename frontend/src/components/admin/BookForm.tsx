import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { api } from "../../api";
import { ErrorBanner } from "../ErrorBanner";
import { isValidIsbn13 } from "../../lib/isbn";
import type { Author, Book, Genre } from "../../types";
import { ChipSelect } from "./ChipSelect";

interface Props {
  /** `undefined` = alta; con un libro = edición (el ISBN es la PK y no se toca). */
  book?: Book;
  authors: Author[];
  genres: Genre[];
  onSaved: () => void;
  onCancel: () => void;
}

/** Espejo de `storage.ALLOWED_CONTENT_TYPES` y `COVER_MAX_BYTES` en la API. */
const COVER_TYPES = ["image/jpeg", "image/png", "image/webp"];
const COVER_MAX_BYTES = 5 * 1024 * 1024;

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

  // Portada: el archivo elegido todavía no está en S3. Se sube después de guardar el
  // libro, porque la URL firmada se pide por ISBN y en un alta el libro aún no existe.
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
  const [removeCover, setRemoveCover] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // La preview es un blob local: hay que liberarlo o queda retenido hasta recargar.
  useEffect(() => {
    if (coverFile === null) {
      setCoverPreview(null);
      return;
    }
    const url = URL.createObjectURL(coverFile);
    setCoverPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [coverFile]);

  const handleCoverChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    if (file === null) {
      setCoverFile(null);
      return;
    }
    // Las mismas dos reglas que aplica la API al firmar: mejor decirlo antes de subir.
    if (!COVER_TYPES.includes(file.type)) {
      setError("La portada tiene que ser JPG, PNG o WebP.");
      event.target.value = "";
      return;
    }
    if (file.size > COVER_MAX_BYTES) {
      setError(`La portada no puede superar ${COVER_MAX_BYTES / (1024 * 1024)} MB.`);
      event.target.value = "";
      return;
    }
    setError(null);
    setRemoveCover(false);
    setCoverFile(file);
  };

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

      const saved = editing
        ? await api.books.update(book.isbn, fields)
        : await api.books.create({ isbn, ...fields });

      // La portada va después y aparte: el libro ya está guardado, así que si la subida
      // falla se avisa sin perder el resto de la carga.
      try {
        if (coverFile !== null) {
          await api.books.uploadCover(saved.isbn, coverFile);
        } else if (removeCover) {
          await api.books.removeCover(saved.isbn);
        }
      } catch (coverError) {
        setError(
          `El libro se guardó, pero la portada no se pudo subir: ${
            coverError instanceof Error ? coverError.message : "error desconocido"
          }. Probá de nuevo editándolo.`
        );
        setSubmitting(false);
        return;
      }

      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  // Qué mostrar en el recuadro: lo recién elegido, lo que ya tenía, o nada.
  const shownCover = coverPreview ?? (removeCover ? null : book?.cover_url ?? null);

  return (
    <form className="form-card" onSubmit={handleSubmit}>
      <h3>{editing ? `Editar «${book.title}»` : "Nuevo libro"}</h3>

      <ErrorBanner
        error={error}
        overrides={{
          409: "Ya existe un libro con ese ISBN.",
          404: "Alguno de los autores o géneros elegidos ya no existe. Recargá la página.",
        }}
      />

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

      <div className="cover-field">
        <span className="cover-field-label">Portada</span>
        <div className="cover-field-row">
          <div className="cover-preview">
            {shownCover ? (
              <img src={shownCover} alt="" />
            ) : (
              <span className="cover-preview-empty">Sin portada</span>
            )}
          </div>
          <div className="cover-field-controls">
            <input type="file" accept={COVER_TYPES.join(",")} onChange={handleCoverChange} />
            <span className="field-hint">
              JPG, PNG o WebP, hasta {COVER_MAX_BYTES / (1024 * 1024)} MB. Se sube directo
              al bucket cuando guardás.
            </span>
            {shownCover && (
              <button
                type="button"
                className="row-button danger"
                onClick={() => {
                  setCoverFile(null);
                  // Solo hay algo que borrar en el servidor si el libro ya tenía portada.
                  setRemoveCover(book?.cover_url != null);
                }}
                disabled={submitting}
              >
                Quitar portada
              </button>
            )}
          </div>
        </div>
      </div>

      <ChipSelect
        label="Autores"
        options={authors}
        selectedIds={authorIds}
        onChange={setAuthorIds}
        placeholder="Agregar autor..."
        emptyText="Todavía no elegiste ningún autor."
        exhaustedText="Ya agregaste todos los autores del catálogo"
      />

      <ChipSelect
        label="Géneros"
        options={genres}
        selectedIds={genreIds}
        onChange={setGenreIds}
        placeholder="Agregar género..."
        emptyText="Todavía no elegiste ningún género."
        exhaustedText="Ya agregaste todos los géneros del catálogo"
      />

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
