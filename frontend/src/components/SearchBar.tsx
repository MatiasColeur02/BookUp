import { type FormEvent } from "react";
import { SearchIcon } from "./icons";

interface Props {
  /** Controlado desde la pantalla: sacar el chip del texto también vacía el input. */
  value: string;
  onValueChange: (value: string) => void;
  onSearch: (query: string) => void;
  /** Volver al catálogo completo: vaciar el input y darle Buscar, o el botón de limpiar. */
  onClear: () => void;
  loading?: boolean;
}

export function SearchBar({ value, onValueChange, onSearch, onClear, loading }: Props) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const query = value.trim();
    if (query) onSearch(query);
    else onClear();
  };

  return (
    <form className="search-bar" onSubmit={handleSubmit}>
      <SearchIcon className="search-bar-icon" />
      <input
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        placeholder="Buscar por título, autor, ISBN o sinopsis..."
      />
      {value !== "" && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
          Limpiar
        </button>
      )}
      <button type="submit" className="btn btn-primary" disabled={loading}>
        {loading ? "Buscando..." : "Buscar"}
      </button>
    </form>
  );
}
