import { useState, type FormEvent } from "react";
import { SearchIcon } from "./icons";

interface Props {
  onSearch: (query: string) => void;
  /** Volver al catálogo: vaciar el input y darle Buscar, o el botón de limpiar. */
  onClear: () => void;
  loading?: boolean;
}

export function SearchBar({ onSearch, onClear, loading }: Props) {
  const [value, setValue] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const query = value.trim();
    if (query) onSearch(query);
    else onClear();
  };

  const handleClear = () => {
    setValue("");
    onClear();
  };

  return (
    <form className="search-bar" onSubmit={handleSubmit}>
      <SearchIcon className="search-bar-icon" />
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Buscar por título, autor, ISBN o sinopsis..."
      />
      {value !== "" && (
        <button type="button" className="search-bar-clear" onClick={handleClear}>
          Limpiar
        </button>
      )}
      <button type="submit" disabled={loading}>
        {loading ? "Buscando..." : "Buscar"}
      </button>
    </form>
  );
}
