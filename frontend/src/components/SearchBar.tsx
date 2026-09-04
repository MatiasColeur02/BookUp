import { useState, type FormEvent } from "react";
import { SearchIcon } from "./icons";

interface Props {
  onSearch: (query: string) => void;
  loading?: boolean;
}

export function SearchBar({ onSearch, loading }: Props) {
  const [value, setValue] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (value.trim()) onSearch(value.trim());
  };

  return (
    <form className="search-bar" onSubmit={handleSubmit}>
      <SearchIcon className="search-bar-icon" />
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Buscar por título, autor, ISBN o sinopsis..."
      />
      <button type="submit" disabled={loading}>
        {loading ? "Buscando..." : "Buscar"}
      </button>
    </form>
  );
}
