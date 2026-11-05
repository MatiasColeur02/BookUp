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
import { ForgotPasswordForm } from "./components/ForgotPasswordForm";
import { LibrarianPanel } from "./components/LibrarianPanel";
import { LibrariesView } from "./components/LibrariesView";
import { LoginForm } from "./components/LoginForm";
import { Logo } from "./components/Logo";
import { MyReservationsView } from "./components/MyReservationsView";
import { ProfileView } from "./components/ProfileView";
import { RegisterForm } from "./components/RegisterForm";
import { RequireRole } from "./components/RequireRole";
import { useSession } from "./context/SessionContext";
import { isCognito } from "./lib/auth";

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

  // Después de ingresar se vuelve a la pantalla en la que estaba (el mismo `from` que
  // guarda `RequireRole`). Desde las pantallas de ingreso no hay a dónde volver.
  const onAuthScreen = ["/login", "/registro", "/recuperar"].includes(location.pathname);
  const state = onAuthScreen ? location.state : { from: location };

  return (
    <div className="session">
      <Link to="/login" state={state} className="btn btn-ghost">
        Ingresar
      </Link>
      <Link to="/registro" state={state} className="btn btn-primary">
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
          {/* Los mismos formularios en los dos modos: con Cognito llaman al User Pool
              (`lib/auth.ts`) en lugar de a la API. */}
          <Route path="/login" element={<LoginForm />} />
          <Route path="/registro" element={<RegisterForm />} />
          {/* Recuperar la contraseña es de Cognito: en `local` no hay emails. */}
          <Route
            path="/recuperar"
            element={isCognito ? <ForgotPasswordForm /> : <Navigate to="/login" replace />}
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
