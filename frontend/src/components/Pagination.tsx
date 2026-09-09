interface Props {
  /** Página actual, empezando en 1. */
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}

/** Cuántos números se muestran alrededor del actual antes de cortar con puntos. */
const WINDOW = 1;

/**
 * Los números a dibujar: siempre la primera y la última, más la actual y sus vecinas.
 * Los huecos se colapsan en un "…", así el control no crece de ancho por más páginas
 * que haya.
 */
export function pageItems(page: number, totalPages: number): (number | "gap")[] {
  // Con pocas páginas no hace falta cortar nada.
  if (totalPages <= 5 + WINDOW * 2) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages = new Set<number>([1, totalPages]);
  for (let value = page - WINDOW; value <= page + WINDOW; value += 1) {
    if (value > 1 && value < totalPages) pages.add(value);
  }

  const sorted = [...pages].sort((a, b) => a - b);
  const items: (number | "gap")[] = [];
  let previous = 0;
  for (const value of sorted) {
    // Un solo número salteado no merece un "…": ocupa lo mismo y se puede clickear.
    if (previous && value - previous === 2) items.push(previous + 1);
    else if (previous && value - previous > 2) items.push("gap");
    items.push(value);
    previous = value;
  }
  return items;
}

/**
 * Paginación numerada del catálogo, al pie de la grilla. Cambiar de página vuelve al
 * principio de la lista (lo hace la pantalla): si no, la página nueva arrancaría a
 * mitad de scroll.
 */
export function Pagination({ page, totalPages, onChange }: Props) {
  if (totalPages <= 1) return null;

  return (
    <nav className="pagination" aria-label="Paginación del catálogo">
      <button
        type="button"
        className="btn btn-secondary btn-icon"
        onClick={() => onChange(page - 1)}
        disabled={page === 1}
        aria-label="Página anterior"
      >
        ‹
      </button>

      <ul className="pagination-pages">
        {pageItems(page, totalPages).map((item, index) =>
          item === "gap" ? (
            <li key={`gap-${index}`} className="pagination-gap" aria-hidden="true">
              …
            </li>
          ) : (
            <li key={item}>
              <button
                type="button"
                className={`pagination-page${item === page ? " active" : ""}`}
                onClick={() => onChange(item)}
                // `aria-current` y no solo la clase: un lector de pantalla tiene que
                // saber en qué página está, no solo verlo.
                aria-current={item === page ? "page" : undefined}
                aria-label={`Página ${item}`}
              >
                {item}
              </button>
            </li>
          )
        )}
      </ul>

      <button
        type="button"
        className="btn btn-secondary btn-icon"
        onClick={() => onChange(page + 1)}
        disabled={page === totalPages}
        aria-label="Página siguiente"
      >
        ›
      </button>
    </nav>
  );
}
