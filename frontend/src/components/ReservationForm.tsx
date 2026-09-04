import { useState, type FormEvent } from "react";

interface Props {
  copyId: number;
  submitting?: boolean;
  onSubmit: (data: { patron_name: string; patron_email: string }) => void;
  onCancel: () => void;
}

export function ReservationForm({ copyId, submitting, onSubmit, onCancel }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({ patron_name: name, patron_email: email });
  };

  return (
    <form className="reservation-form" onSubmit={handleSubmit}>
      <h3>
        Reservar ejemplar <span className="badge">#{copyId}</span>
      </h3>
      <label>
        Nombre
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <label>
        Email
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
      </label>
      <div className="actions">
        <button type="button" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="submit" disabled={submitting}>
          {submitting ? "Reservando..." : "Confirmar reserva"}
        </button>
      </div>
    </form>
  );
}
