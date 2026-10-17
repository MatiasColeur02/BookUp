import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
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
import { HostedUiRedirect } from "./components/HostedUiRedirect";
import { LibrarianPanel } from "./components/LibrarianPanel";
import { LibrariesView } from "./components/LibrariesView";
import { LoginForm } from "./components/LoginForm";
import { Logo } from "./components/Logo";
import { MyReservationsView } from "./components/MyReservationsView";
import { ProfileView } from "./components/ProfileView";
import { RegisterForm } from "./components/RegisterForm";
import { RequireRole } from "./components/RequireRole";
import { useSession } from "./context/SessionContext";
import { isCognito, startLogin, startSignup } from "./lib/auth";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "active" : "";
}

/**
 * Solo los accesos de entrada. Con sesión abierta el header no muestra nada: quién sos
 * y el cierre de sesión viven en «Mi perfil», que ya está en la navegación.
 */
function SessionMenu() {
  const { user, loading } = useSession();
  const location = useLocation();

  if (loading) return <span className="muted">Cargando sesión...</span>;
  if (user) return null;

  if (isCognito) {
    // Directo a la Hosted UI, volviendo a la pantalla en la que estaba.
    const here = `${location.pathname}${location.search}`;
    return (
      <div className="session">
        <button type="button" className="btn btn-ghost" onClick={() => startLogin(here)}>
          Ingresar
        </button>
        <button type="button" className="btn btn-primary" onClick={() => startSignup(here)}>
          Crear cuenta
        </button>
      </div>
    );
  }

  return (
    <div className="session">
      <Link to="/login" className="btn btn-ghost">
        Ingresar
      </Link>
      <Link to="/registro" className="btn btn-primary">
        Crear cuenta
      </Link>
    </div>
  );
}

export default function App() {
  const { user, isLibrarian, isSysadmin } = useSession();
  const canSeePanel = isLibrarian || isSysadmin;

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-top">
          <Link to="/" className="brand">
            <Logo className="brand-mark" />
            <div>
              <h1>BookUp</h1>
              <p className="tagline">Catálogo y reservas de la red de bibliotecas</p>
            </div>
          </Link>
          <SessionMenu />
        </div>
        <nav className="segmented" aria-label="Secciones">
          <NavLink to="/" className={navClass} end>
            Catálogo
          </NavLink>
          {user && (
            <NavLink to="/mis-reservas" className={navClass}>
              Mis reservas
            </NavLink>
          )}
          <NavLink to="/sedes" className={navClass}>
            Sedes
          </NavLink>
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
      </header>
      <ApiStatus />
      <main>
        <Routes>
          <Route path="/" element={<CatalogView />} />
          <Route path="/sedes" element={<LibrariesView />} />
          {/* Con Cognito no hay formularios propios: las rutas salen a la Hosted UI. */}
          <Route
            path="/login"
            element={isCognito ? <HostedUiRedirect page="login" /> : <LoginForm />}
          />
          <Route
            path="/registro"
            element={isCognito ? <HostedUiRedirect page="signup" /> : <RegisterForm />}
          />
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
