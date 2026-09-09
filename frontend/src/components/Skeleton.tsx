/**
 * Placeholders de carga. Tienen la forma de lo que viene después, así la pantalla no
 * salta cuando llegan los datos. El aspecto (color y barrido) vive en `.skeleton`.
 */

/** Filas de una tabla que todavía está cargando. */
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton skeleton-row" />
      ))}
    </div>
  );
}
