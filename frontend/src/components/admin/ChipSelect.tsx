interface Option {
  id: number;
  name: string;
}

interface Props {
  label: string;
  options: Option[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  /** Texto de la opción vacía del desplegable. Ej: "Agregar autor...". */
  placeholder: string;
  /** Qué decir cuando todavía no se eligió nada. */
  emptyText: string;
  /** Qué decir cuando ya no quedan opciones sin elegir. */
  exhaustedText: string;
}

/**
 * Elegir de a uno desde un desplegable, y ver lo elegido como chips debajo.
 *
 * Reemplaza al `<select multiple>`, que obliga a Ctrl/Cmd + clic, no muestra la
 * selección de un vistazo y es fácil de vaciar sin querer — un riesgo real acá,
 * porque mandar estas listas en un PATCH reemplaza la lista completa del libro.
 */
export function ChipSelect({
  label,
  options,
  selectedIds,
  onChange,
  placeholder,
  emptyText,
  exhaustedText,
}: Props) {
  // El desplegable solo ofrece lo que todavía no está elegido: no se puede repetir.
  const available = options.filter((option) => !selectedIds.includes(option.id));
  const nameFor = (id: number) => options.find((option) => option.id === id)?.name ?? `#${id}`;

  const add = (id: number) => onChange([...selectedIds, id]);
  const remove = (id: number) => onChange(selectedIds.filter((selected) => selected !== id));

  return (
    <div className="chip-select">
      <label>
        {label}
        <select
          // Vuelve siempre al placeholder: el estado real son los chips de abajo.
          value=""
          disabled={available.length === 0}
          onChange={(event) => {
            if (event.target.value !== "") add(Number(event.target.value));
          }}
        >
          <option value="">{available.length === 0 ? exhaustedText : placeholder}</option>
          {available.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>
      </label>

      {selectedIds.length === 0 ? (
        <p className="chips-empty">{emptyText}</p>
      ) : (
        <ul className="chips">
          {selectedIds.map((id) => (
            <li key={id} className="chip">
              <span>{nameFor(id)}</span>
              <button
                type="button"
                className="chip-remove"
                onClick={() => remove(id)}
                aria-label={`Quitar ${nameFor(id)}`}
                title={`Quitar ${nameFor(id)}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
