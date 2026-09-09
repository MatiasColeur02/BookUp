import { useEffect, useState } from "react";
import { api } from "../api";
import type { Author, Genre } from "../types";

export interface CatalogFilterState {
  authorIds: number[];
  genreIds: number[];
  cities: string[];
}

export const EMPTY_FILTERS: CatalogFilterState = { authorIds: [], genreIds: [], cities: [] };

export function countFilters(filters: CatalogFilterState): number {
  return filters.authorIds.length + filters.genreIds.length + filters.cities.length;
}

interface Props {
  filters: CatalogFilterState;
  onChange: (filters: CatalogFilterState) => void;
}

/**
 * Filtros del catálogo: ciudad, género y autor, cada uno multi-selección.
 *
 * El panel arranca cerrado para no tapar la grilla de portadas, pero se abre solo si ya
 * hay filtros puestos (por ejemplo al volver con una URL compartida). Las opciones se
 * cargan una vez: son datos de referencia que casi no cambian y la API los cachea 600 s.
 *
 * La ciudad no sale de `/libraries` sino de `/books/cities`, que devuelve solo las que
 * hoy tienen stock disponible: ofrecer una ciudad que va a dar cero resultados es peor
 * que no ofrecerla.
 */
export function CatalogFilters({ filters, onChange }: Props) {
  const [open, setOpen] = useState(() => countFilters(filters) > 0);
  const [authors, setAuthors] = useState<Author[]>([]);
  const [genres, setGenres] = useState<Genre[]>([]);
  const [cities, setCities] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.authors.list(), api.genres.list(), api.books.cities()])
      .then(([nextAuthors, nextGenres, nextCities]) => {
        if (cancelled) return;
        setAuthors(nextAuthors);
        setGenres(nextGenres);
        setCities(nextCities);
      })
      // Si no cargan, la pantalla sigue funcionando sin filtros: no vale un error.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const active = countFilters(filters);

  const toggleId = (key: "authorIds" | "genreIds", id: number) => {
    const current = filters[key];
    onChange({
      ...filters,
      [key]: current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    });
  };

  const toggleCity = (city: string) => {
    onChange({
      ...filters,
      cities: filters.cities.includes(city)
        ? filters.cities.filter((value) => value !== city)
        : [...filters.cities, city],
    });
  };

  return (
    <div className="catalog-filters">
      <div className="catalog-filters-bar">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
        >
          Filtros
          {active > 0 && <span className="badge badge-accent">{active}</span>}
        </button>

        {active > 0 && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange(EMPTY_FILTERS)}>
            Limpiar filtros
          </button>
        )}
      </div>

      {open && (
        <div className="catalog-filters-panel">
          <FilterGroup
            label="Ciudad"
            hint="Con ejemplar disponible hoy"
            options={cities.map((city) => ({ key: city, label: city }))}
            isSelected={(key) => filters.cities.includes(String(key))}
            onToggle={(key) => toggleCity(String(key))}
          />
          <FilterGroup
            label="Género"
            options={genres.map((genre) => ({ key: genre.id, label: genre.name }))}
            isSelected={(key) => filters.genreIds.includes(Number(key))}
            onToggle={(key) => toggleId("genreIds", Number(key))}
          />
          <FilterGroup
            label="Autor"
            options={authors.map((author) => ({ key: author.id, label: author.name }))}
            isSelected={(key) => filters.authorIds.includes(Number(key))}
            onToggle={(key) => toggleId("authorIds", Number(key))}
          />
        </div>
      )}
    </div>
  );
}

interface GroupProps {
  label: string;
  hint?: string;
  options: { key: string | number; label: string }[];
  isSelected: (key: string | number) => boolean;
  onToggle: (key: string | number) => void;
}

/**
 * Un grupo de opciones como botones que se prenden y apagan. Son `aria-pressed` y no
 * checkboxes porque cada uno dispara una búsqueda: se comportan como un toggle, no como
 * un formulario que después se envía.
 */
function FilterGroup({ label, hint, options, isSelected, onToggle }: GroupProps) {
  if (options.length === 0) return null;

  return (
    <div className="filter-group">
      <p className="filter-group-label">
        {label}
        {hint && <span className="filter-group-hint">{hint}</span>}
      </p>
      <div className="filter-options">
        {options.map(({ key, label: optionLabel }) => (
          <button
            key={key}
            type="button"
            className={`filter-chip${isSelected(key) ? " active" : ""}`}
            aria-pressed={isSelected(key)}
            onClick={() => onToggle(key)}
          >
            {optionLabel}
          </button>
        ))}
      </div>
    </div>
  );
}
