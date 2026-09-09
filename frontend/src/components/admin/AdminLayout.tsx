import type { ComponentType } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import {
  BookIcon,
  CopiesIcon,
  PenIcon,
  PinIcon,
  TagIcon,
  ToolIcon,
  UsersIcon,
} from "../icons";

interface Section {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  sysadminOnly: boolean;
}

const SECTIONS: Section[] = [
  { to: "/gestion/libros", label: "Libros", icon: BookIcon, sysadminOnly: false },
  { to: "/gestion/autores", label: "Autores", icon: PenIcon, sysadminOnly: false },
  { to: "/gestion/generos", label: "Géneros", icon: TagIcon, sysadminOnly: false },
  { to: "/gestion/ejemplares", label: "Ejemplares", icon: CopiesIcon, sysadminOnly: false },
  // Un `librarian` entra acá para editar su propia sede; el alta y la baja son de `sysadmin`.
  { to: "/gestion/sedes", label: "Sedes", icon: PinIcon, sysadminOnly: false },
  { to: "/gestion/usuarios", label: "Usuarios", icon: UsersIcon, sysadminOnly: true },
  { to: "/gestion/mantenimiento", label: "Mantenimiento", icon: ToolIcon, sysadminOnly: true },
];

/**
 * Gestión: navegación lateral en desktop, tira horizontal scrolleable en mobile.
 * Las dos formas son la misma lista; la diferencia la resuelve el CSS (`.admin-nav`).
 */
export function AdminLayout() {
  const { isSysadmin } = useSession();
  const sections = SECTIONS.filter((section) => isSysadmin || !section.sysadminOnly);

  return (
    <div className="admin">
      <nav className="admin-nav" aria-label="Secciones de gestión">
        {sections.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="admin-content">
        <Outlet />
      </div>
    </div>
  );
}
