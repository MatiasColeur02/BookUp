import { NavLink, Outlet } from "react-router-dom";

const SECTIONS = [
  { to: "/gestion/libros", label: "Libros" },
  { to: "/gestion/autores", label: "Autores" },
  { to: "/gestion/generos", label: "Géneros" },
  { to: "/gestion/ejemplares", label: "Ejemplares" },
];

export function AdminLayout() {
  return (
    <div className="admin">
      <nav className="tabs subtabs">
        {SECTIONS.map(({ to, label }) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
