import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthRedirectNotice } from "./components/AuthRedirectNotice";
import { SessionProvider } from "./context/SessionContext";
import { ConfirmProvider } from "./context/ConfirmContext";
import { ThemeProvider } from "./context/ThemeContext";
import { ToastProvider } from "./context/ToastContext";
import { consumeAuthRedirect } from "./lib/auth";
import "./index.css";

// Antes de montar React: si volvemos del login de Cognito con `#access_token=…`, el token
// queda guardado y la URL en la ruta destino, así `SessionProvider` arranca con la sesión y
// el router con la ruta correcta (no con `/` y un fragmento a la vista).
consumeAuthRedirect();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <SessionProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AuthRedirectNotice />
              <App />
            </ConfirmProvider>
          </ToastProvider>
        </SessionProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
