import { useCallback } from "react";
import { api } from "../../api";
import { NameResourceAdmin } from "./NameResourceAdmin";

export function AuthorsAdmin() {
  const list = useCallback(() => api.authors.list(), []);
  const create = useCallback((name: string) => api.authors.create({ name }), []);
  const update = useCallback((id: number, name: string) => api.authors.update(id, { name }), []);
  const remove = useCallback((id: number) => api.authors.remove(id), []);

  return (
    <NameResourceAdmin
      title="Autores"
      singular="el autor"
      // `Author.name` no es unique en el modelo: la identidad es el id.
      hint="Se permiten homónimos: dos autores distintos pueden llamarse igual, y crear el mismo nombre dos veces genera dos autores separados."
      list={list}
      create={create}
      update={update}
      remove={remove}
      inUseMessage="No se puede eliminar: el autor todavía está asociado a algún libro. Sacalo de esos libros primero."
    />
  );
}
