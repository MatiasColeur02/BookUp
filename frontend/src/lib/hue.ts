/**
 * Tono estable a partir de un texto.
 *
 * Es el mismo criterio que usan las portadas sin imagen (`BookCover`) y los chips de
 * filtro activo: un valor siempre tiene el mismo color, y ese color no se elige a mano.
 * La saturación y la luminosidad las fija el tema con los tokens `--cover-*`, así que
 * ningún tono puede quedar estridente ni ilegible, ni en claro ni en oscuro.
 */
export function hueFrom(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) % 360;
  }
  return hash;
}
