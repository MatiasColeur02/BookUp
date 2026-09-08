import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../../context/SessionContext";

const SECTIONS = [
  { to: "/gestion/libros", label: "Libros", sysadminOnly: false },
  { to: "/gestion/autores", label: "Autores", sysadminOnly: false },
  { to: "/gestion/generos", label: "Géneros", sysadminOnly: false },
  { to: "/gestion/ejemplares", label: "Ejemplares", sysadminOnly: false },
  // Un `librarian` entra acá para editar su propia sede; el alta y la baja son de `sysadmin`.
  { to: "/gestion/sedes", label: "Sedes", sysadminOnly: false },
  { to: "/gestion/usuarios", label: "Usuarios", sysadminOnly: true },
  { to: "/gestion/mantenimiento", label: "Mantenimiento", sysadminOnly: true },
];

export function AdminLayout() {
  const { isSysadmin } = useSession();
  const sections = SECTIONS.filter((section) => isSysadmin || !section.sysadminOnly);

  return (
    <div className="admin">
      <nav className="tabs subtabs">
        {sections.map(({ to, label }) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
