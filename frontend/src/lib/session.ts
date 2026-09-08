const STORAGE_KEY = "bookup.token";

type Listener = (token: string | null) => void;

const listeners = new Set<Listener>();

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    // localStorage puede no estar disponible (modo privado estricto, etc.).
    return null;
  }
}

let token: string | null = readStoredToken();

function notify(): void {
  for (const listener of listeners) listener(token);
}

export function getToken(): string | null {
  return token;
}

export function setToken(next: string): void {
  token = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Sin persistencia la sesión no sobrevive un refresh, pero sigue andando en
    // memoria durante esta pestaña.
  }
  notify();
}

export function clearToken(): void {
  token = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ver setToken: mismo fallback.
  }
  notify();
}

/**
 * El token puede cambiar desde afuera de React (el interceptor de 401 en `api.ts`
 * lo limpia), así que `SessionContext` necesita enterarse sin pasar por props.
 */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
