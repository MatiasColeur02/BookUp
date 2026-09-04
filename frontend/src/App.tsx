import { useState } from "react";
import { CatalogView } from "./components/CatalogView";
import { LibrarianPanel } from "./components/LibrarianPanel";

type View = "catalog" | "librarian";

export default function App() {
  const [view, setView] = useState<View>("catalog");

  return (
    <div className="app">
      <header className="app-header">
        <h1>BookUp</h1>
        <nav>
          <button className={view === "catalog" ? "active" : ""} onClick={() => setView("catalog")}>
            Catálogo
          </button>
          <button className={view === "librarian" ? "active" : ""} onClick={() => setView("librarian")}>
            Panel bibliotecario
          </button>
        </nav>
      </header>
      <main>{view === "catalog" ? <CatalogView /> : <LibrarianPanel />}</main>
    </div>
  );
}
