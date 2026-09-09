import type { ReactNode } from "react";
import { CheckIcon } from "./icons";
import { Modal } from "./Modal";

export type ConfirmTone = "positive" | "danger";

export interface ConfirmOptions {
  title: string;
  /** El cuerpo: qué va a pasar y qué no se puede deshacer. */
  message?: ReactNode;
  /** Datos de lo que se está por tocar, para no confirmar a ciegas. */
  details?: { label: string; value: ReactNode }[];
  confirmLabel?: string;
  cancelLabel?: string;
  /** `positive` confirma algo que suma (verde); `danger`, algo que se pierde (rojo). */
  tone?: ConfirmTone;
}

interface Props extends ConfirmOptions {
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Diálogo de confirmación. Es el reemplazo de `window.confirm`, que no seguía ningún
 * diseño y no deja mostrar el detalle de lo que se está por hacer.
 *
 * Se monta sobre `Modal`, así hereda Escape, click en el fondo y el bloqueo de scroll,
 * pero se dibuja por encima: hay acciones que se confirman desde adentro de otro modal
 * (cancelar una reserva desde el panel del bibliotecario).
 */
export function ConfirmDialog({
  title,
  message,
  details,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  tone = "danger",
  onConfirm,
  onCancel,
}: Props) {
  return (
    <Modal title={title} onClose={onCancel} className="modal-over">
      <div className={`card stack confirm confirm-${tone}`}>
        <div className="confirm-head">
          <span className="confirm-icon" aria-hidden="true">
            {tone === "positive" ? <CheckIcon /> : "!"}
          </span>
          <h3>{title}</h3>
        </div>

        {message && <p className="confirm-message">{message}</p>}

        {details && details.length > 0 && (
          <dl className="detail-grid confirm-details">
            {details.map(({ label, value }) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}

        <div className="actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn ${tone === "positive" ? "btn-success" : "btn-danger-solid"}`}
            onClick={onConfirm}
            // El foco arranca acá: confirmar es lo que la persona vino a hacer, y con
            // Enter se cierra sin tener que tabular.
            autoFocus
          >
            {tone === "positive" && <CheckIcon />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
