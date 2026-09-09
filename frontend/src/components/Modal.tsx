import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  /** Nombre accesible del diálogo; el título visible lo pone el contenido. */
  title: string;
  onClose: () => void;
  /** Clase extra en el fondo. `modal-over` lo dibuja encima de otro modal abierto. */
  className?: string;
  children: ReactNode;
}

export function Modal({ title, onClose, className, children }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  // El `onClose` del padre suele ser una arrow nueva en cada render: si entrara como
  // dependencia del efecto, el foco se robaría de vuelta al diálogo en cada tecla.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", handleKeyDown);

    // El fondo no scrollea mientras el diálogo está abierto.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  // Se monta fuera del árbol de la pantalla para que ningún `overflow` de un contenedor
  // recorte el diálogo.
  return createPortal(
    <div
      className={`modal-backdrop${className ? ` ${className}` : ""}`}
      // `mousedown` y no `click`: si el gesto empezó adentro (seleccionar texto) y
      // terminó afuera, el diálogo no se tiene que cerrar.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={dialogRef}
      >
        <button type="button" className="btn btn-ghost btn-icon modal-close" onClick={onClose} aria-label="Cerrar">
          ×
        </button>
        {children}
      </div>
    </div>,
    document.body
  );
}
