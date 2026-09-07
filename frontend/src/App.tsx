import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { CatalogView } from "./components/CatalogView";
import { BookIcon } from "./components/icons";
import { LibrarianPanel } from "./components/LibrarianPanel";

export default function App() {
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
          <NavLink to="/" className={({ isActive }) => (isActive ? "active" : "")} end>
            Catálogo
          </NavLink>
          <NavLink to="/panel" className={({ isActive }) => (isActive ? "active" : "")}>
            Panel bibliotecario
          </NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CatalogView />} />
          <Route path="/panel" element={<LibrarianPanel />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
