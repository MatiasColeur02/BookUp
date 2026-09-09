import { useEffect, useState } from "react";
import { api } from "../api";
import type { Author, Genre } from "../types";

export interface CatalogFilterOptions {
  authors: Author[];
  genres: Genre[];
  cities: string[];
}

const EMPTY: CatalogFilterOptions = { authors: [], genres: [], cities: [] };

/**
 * Opciones de los filtros del catálogo, cargadas una sola vez.
 *
 * Viven acá arriba y no adentro del panel de filtros porque también hacen falta para
 * poner nombre a los filtros activos: el estado guarda ids (`genre_id=3`), y el chip
 * tiene que decir «Novela».
 *
 * Las ciudades salen de `/books/cities` y no de `/libraries`: son las que hoy tienen
 * stock disponible, que es lo único que el filtro puede devolver.
 */
export function useCatalogFilterOptions(): CatalogFilterOptions {
  const [options, setOptions] = useState<CatalogFilterOptions>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.authors.list(), api.genres.list(), api.books.cities()])
      .then(([authors, genres, cities]) => {
        if (!cancelled) setOptions({ authors, genres, cities });
      })
      // Si no cargan, la pantalla sigue funcionando sin filtros: no vale un error.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return options;
}
