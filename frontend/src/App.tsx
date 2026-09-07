import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { CatalogView } from "./components/CatalogView";
import { BookIcon } from "./components/icons";
import { LibrarianPanel } from "./components/LibrarianPanel";
import { LoginForm } from "./components/LoginForm";
import { MyReservationsView } from "./components/MyReservationsView";
import { ProfileView } from "./components/ProfileView";
import { RegisterForm } from "./components/RegisterForm";
import { RequireRole } from "./components/RequireRole";
import { useSession } from "./context/SessionContext";
import { roleLabel } from "./lib/roles";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "active" : "";
}

function SessionMenu() {
  const { user, loading, logout } = useSession();

  if (loading) return <span className="muted">Cargando sesión...</span>;

  if (!user) {
    return (
      <div className="session">
        <Link to="/login" className="session-link">
          Ingresar
        </Link>
        <Link to="/registro" className="session-link primary">
          Crear cuenta
        </Link>
      </div>
    );
  }

  return (
    <div className="session">
      <Link to="/perfil" className="session-user">
        <strong>{user.name}</strong>
        <span className="role-chip">{roleLabel(user.role)}</span>
      </Link>
      <button type="button" className="session-link" onClick={logout}>
        Cerrar sesión
      </button>
    </div>
  );
}

export default function App() {
  const { user, isLibrarian, isSysadmin } = useSession();
  const canSeePanel = isLibrarian || isSysadmin;

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark">
            <BookIcon />
          </span>
          <div>
            <h1>BookUp</h1>
            <p className="tagline">Catálogo y reservas de la red de bibliotecas</p>
          </div>
        </div>
        <nav className="tabs">
          <NavLink to="/" className={navClass} end>
            Catálogo
          </NavLink>
          {user && (
            <NavLink to="/mis-reservas" className={navClass}>
              Mis reservas
            </NavLink>
          )}
          {canSeePanel && (
            <NavLink to="/panel" className={navClass}>
              Panel bibliotecario
            </NavLink>
          )}
          {user && (
            <NavLink to="/perfil" className={navClass}>
              Mi perfil
            </NavLink>
          )}
        </nav>
        <SessionMenu />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CatalogView />} />
          <Route path="/login" element={<LoginForm />} />
          <Route path="/registro" element={<RegisterForm />} />
          <Route
            path="/mis-reservas"
            element={
              <RequireRole>
                <MyReservationsView />
              </RequireRole>
            }
          />
          <Route
            path="/perfil"
            element={
              <RequireRole>
                <ProfileView />
              </RequireRole>
            }
          />
          <Route
            path="/panel"
            element={
              <RequireRole roles={["librarian", "sysadmin"]}>
                <LibrarianPanel />
              </RequireRole>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
