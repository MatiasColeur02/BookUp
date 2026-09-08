import { useEffect, useState } from "react";
import { api } from "../api";

const CHECK_INTERVAL_MS = 30_000;

/**
 * Indicador de API caída. Sin esto, un backend apagado se ve igual que un catálogo
 * vacío: "no hay resultados" en vez de "no hay servidor".
 *
 * No muestra nada mientras la API responde: solo aparece cuando algo falla.
 */
export function ApiStatus() {
  const [reachable, setReachable] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const check = () => {
      api
        .health()
        .then(() => {
          if (!cancelled) setReachable(true);
        })
        .catch(() => {
          if (!cancelled) setReachable(false);
        });
    };

    check();
    const timer = window.setInterval(check, CHECK_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (reachable) return null;

  return (
    <p className="api-status" role="status">
      No hay conexión con la API. Lo que veas puede estar incompleto o desactualizado.
    </p>
  );
}
