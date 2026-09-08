import { useCallback } from "react";
import { api } from "../../api";
import { NameResourceAdmin } from "./NameResourceAdmin";

export function GenresAdmin() {
  const list = useCallback(() => api.genres.list(), []);
  const create = useCallback((name: string) => api.genres.create({ name }), []);
  const update = useCallback((id: number, name: string) => api.genres.update(id, { name }), []);
  const remove = useCallback((id: number) => api.genres.remove(id), []);

  return (
    <NameResourceAdmin
      title="Géneros"
      singular="el género"
      // A diferencia de los autores, `Genre.name` sí es unique.
      hint="El nombre es único: si ya existe un género con ese nombre, la API lo rechaza."
      list={list}
      create={create}
      update={update}
      remove={remove}
      duplicateMessage="Ya existe un género con ese nombre."
      inUseMessage="No se puede eliminar: el género todavía está asociado a algún libro. Sacalo de esos libros primero."
    />
  );
}
