import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Book, Library, PhysicalBook } from "../types";

export interface CopyDetails {
  copy?: PhysicalBook;
  book?: Book;
  library?: Library;
}

/**
 * Una `Reservation` solo trae `physical_book_id`. Para mostrar "El Aleph — Sede
 * Centro" en vez de "#12" hay que resolver el ejemplar y, con su `isbn`, el libro.
 *
 * Cachea por id/isbn y no vuelve a pedir lo ya pedido: una lista de reservas del
 * mismo libro dispara una sola llamada. Las sedes se traen de una en el `list`, que es
 * más barato que un `GET /libraries/{id}` por fila.
 *
 * Todo lo que consulta es público, así que funciona igual para un `customer` que para
 * un `librarian`.
 */
export function useCopyDetails(copyIds: number[]): (copyId: number) => CopyDetails {
  const [copies, setCopies] = useState<Record<number, PhysicalBook>>({});
  const [books, setBooks] = useState<Record<string, Book>>({});
  const [libraries, setLibraries] = useState<Record<number, Library>>({});

  // Ids/isbns ya pedidos (aunque la respuesta todavía no haya llegado o haya fallado),
  // para no reintentar en cada render.
  const requestedCopies = useRef(new Set<number>());
  const requestedBooks = useRef(new Set<string>());

  useEffect(() => {
    let cancelled = false;
    api.libraries
      .list()
      .then((all) => {
        if (cancelled) return;
        setLibraries(Object.fromEntries(all.map((library) => [library.id, library])));
      })
      .catch(() => {
        // Sin sedes se muestra el id: no vale la pena romper la vista por esto.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // `copyIds` es un array nuevo en cada render: la dependencia real es su contenido.
  const key = copyIds.join(",");

  useEffect(() => {
    let cancelled = false;

    const pending = copyIds.filter((id) => !requestedCopies.current.has(id));
    for (const id of pending) requestedCopies.current.add(id);

    for (const id of pending) {
      api.physicalBooks
        .get(id)
        .then((copy) => {
          if (cancelled) return;
          setCopies((prev) => ({ ...prev, [copy.id]: copy }));

          if (requestedBooks.current.has(copy.isbn)) return;
          requestedBooks.current.add(copy.isbn);
          return api.books.get(copy.isbn).then((book) => {
            if (!cancelled) setBooks((prev) => ({ ...prev, [book.isbn]: book }));
          });
        })
        .catch(() => {
          // Ejemplar borrado o sin permisos: la fila cae al id crudo.
        });
    }

    return () => {
      cancelled = true;
    };
  }, [key]);

  return (copyId: number): CopyDetails => {
    const copy = copies[copyId];
    return {
      copy,
      book: copy ? books[copy.isbn] : undefined,
      library: copy ? libraries[copy.library_id] : undefined,
    };
  };
}
