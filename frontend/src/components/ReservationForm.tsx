import { useState, type FormEvent } from "react";

interface Props {
  physicalBookId: number;
  submitting?: boolean;
  onSubmit: (data: { name: string; email: string; password: string }) => void;
  onCancel: () => void;
}

export function ReservationForm({ physicalBookId, submitting, onSubmit, onCancel }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({ name, email, password });
  };

  return (
    <form className="reservation-form" onSubmit={handleSubmit}>
      <h3>
        Reservar ejemplar <span className="badge">#{physicalBookId}</span>
      </h3>
      <label>
        Nombre
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <label>
        Email
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
      </label>
      <label>
        Contraseña
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          minLength={8}
          required
        />
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
