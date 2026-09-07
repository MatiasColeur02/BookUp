import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import type { UserRole } from "../types";

interface Props {
  /** Roles habilitados. Omitirlo pide solo estar autenticado. */
  roles?: UserRole[];
  children: ReactNode;
}

/**
 * Guarda de ruta: sin sesión manda a `/login` (recordando a dónde iba, para poder
 * retomar después del login), y con un rol que no alcanza manda al catálogo.
 *
 * Espera a que `loading` termine antes de decidir: si no, un refresh sobre una ruta
 * protegida redirigiría a `/login` mientras `GET /auth/me` todavía está en vuelo.
 */
export function RequireRole({ roles, children }: Props) {
  const { user, loading } = useSession();
  const location = useLocation();

  if (loading) return <p className="muted">Cargando sesión...</p>;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;

  return <>{children}</>;
}
