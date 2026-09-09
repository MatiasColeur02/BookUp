import type { CSSProperties } from "react";
import { hueFrom } from "../lib/hue";
import type { CatalogFilterState } from "./CatalogFilters";
import type { CatalogFilterOptions } from "../hooks/useCatalogFilterOptions";

interface Props {
  /** Texto buscado, si hay: también es un filtro y se puede sacar como los demás. */
  query: string;
  filters: CatalogFilterState;
  options: CatalogFilterOptions;
  onRemoveQuery: () => void;
  onChange: (filters: CatalogFilterState) => void;
}

/**
 * Lo que está filtrando ahora mismo, al lado del título y del conteo de resultados.
 *
 * Cada chip se colorea con el tono derivado de su propio texto, el mismo criterio que
 * usan las portadas sin imagen (`lib/hue.ts`): «Rosario» tiene siempre el mismo color,
 * acá y en la grilla, y la paleta la fija el tema con los tokens `--cover-*`.
 */
export function ActiveFilters({ query, filters, options, onRemoveQuery, onChange }: Props) {
  const nameOf = <T extends { id: number; name: string }>(list: T[], id: number) =>
    list.find((item) => item.id === id)?.name ?? `#${id}`;

  const tags: { key: string; label: string; onRemove: () => void }[] = [];

  if (query !== "") {
    tags.push({ key: `q:${query}`, label: `«${query}»`, onRemove: onRemoveQuery });
  }

  for (const city of filters.cities) {
    tags.push({
      key: `city:${city}`,
      label: city,
      onRemove: () =>
        onChange({ ...filters, cities: filters.cities.filter((value) => value !== city) }),
    });
  }

  for (const id of filters.genreIds) {
    tags.push({
      key: `genre:${id}`,
      label: nameOf(options.genres, id),
      onRemove: () =>
        onChange({ ...filters, genreIds: filters.genreIds.filter((value) => value !== id) }),
    });
  }

  for (const id of filters.authorIds) {
    tags.push({
      key: `author:${id}`,
      label: nameOf(options.authors, id),
      onRemove: () =>
        onChange({ ...filters, authorIds: filters.authorIds.filter((value) => value !== id) }),
    });
  }

  if (tags.length === 0) return null;

  return (
    <ul className="active-filters">
      {tags.map(({ key, label, onRemove }) => (
        <li
          key={key}
          className="filter-tag"
          style={{ "--cover-hue": hueFrom(label) } as CSSProperties}
        >
          <span>{label}</span>
          <button
            type="button"
            className="filter-tag-remove"
            onClick={onRemove}
            aria-label={`Quitar el filtro ${label}`}
            title={`Quitar el filtro ${label}`}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}
