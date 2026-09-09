import { useEffect, useState } from "react";
import type { Book } from "../types";
import { BookIcon } from "./icons";

interface Props {
  book: Pick<Book, "title" | "cover_url">;
  /** `eager` para la portada del detalle, que se ve sí o sí. */
  loading?: "lazy" | "eager";
}

/**
 * Portada de un libro, con reemplazo tipográfico cuando no hay imagen.
 *
 * El placeholder no es un ícono solo: la mayoría del catálogo no tiene portada cargada,
 * y una grilla de íconos iguales no deja distinguir un libro de otro.
 */
export function BookCover({ book, loading = "lazy" }: Props) {
  // Una URL puede quedar rota (objeto borrado del bucket, bucket privado): si la imagen
  // falla, se cae al placeholder en vez de dejar el ícono de imagen rota del browser.
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [book.cover_url]);

  if (!book.cover_url || failed) {
    return (
      <div className="book-cover book-cover-empty" aria-hidden="true">
        <BookIcon />
        <span>{book.title}</span>
      </div>
    );
  }

  return (
    <img
      className="book-cover"
      src={book.cover_url}
      alt={`Portada de ${book.title}`}
      loading={loading}
      onError={() => setFailed(true)}
    />
  );
}
