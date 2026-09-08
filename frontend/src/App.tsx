import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./components/admin/AdminLayout";
import { ApiStatus } from "./components/ApiStatus";
import { AuthorsAdmin } from "./components/admin/AuthorsAdmin";
import { BooksAdmin } from "./components/admin/BooksAdmin";
import { GenresAdmin } from "./components/admin/GenresAdmin";
import { LibrariesAdmin } from "./components/admin/LibrariesAdmin";
import { MaintenanceView } from "./components/admin/MaintenanceView";
import { PhysicalBooksAdmin } from "./components/admin/PhysicalBooksAdmin";
import { UsersAdmin } from "./components/admin/UsersAdmin";
import { CatalogView } from "./components/CatalogView";
import { BookIcon } from "./components/icons";
import { LibrarianPanel } from "./components/LibrarianPanel";
import { LibrariesView } from "./components/LibrariesView";
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
          <NavLink to="/sedes" className={navClass}>
            Sedes
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
          {canSeePanel && (
            <NavLink to="/gestion" className={navClass}>
              Gestión
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
      <ApiStatus />
      <main>
        <Routes>
          <Route path="/" element={<CatalogView />} />
          <Route path="/sedes" element={<LibrariesView />} />
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
          <Route
            path="/gestion"
            element={
              <RequireRole roles={["librarian", "sysadmin"]}>
                <AdminLayout />
              </RequireRole>
            }
          >
            <Route index element={<Navigate to="/gestion/libros" replace />} />
            <Route path="libros" element={<BooksAdmin />} />
            <Route path="autores" element={<AuthorsAdmin />} />
            <Route path="generos" element={<GenresAdmin />} />
            <Route path="ejemplares" element={<PhysicalBooksAdmin />} />
            <Route path="sedes" element={<LibrariesAdmin />} />
            <Route
              path="usuarios"
              element={
                <RequireRole roles={["sysadmin"]}>
                  <UsersAdmin />
                </RequireRole>
              }
            />
            <Route
              path="mantenimiento"
              element={
                <RequireRole roles={["sysadmin"]}>
                  <MaintenanceView />
                </RequireRole>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
