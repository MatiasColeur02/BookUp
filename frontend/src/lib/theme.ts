/**
 * Preferencia de tema. Vive en `localStorage`, no en la API: es una preferencia del
 * dispositivo, y tiene que funcionar sin sesión (el selector está en Mi perfil, pero
 * un visitante anónimo igual merece que se respete el tema de su sistema).
 */

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "bookup:theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export function getStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // Modo privado o storage bloqueado: se cae al default.
  }
  return "system";
}

export function storePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Sin persistencia el tema igual funciona, solo no sobrevive al refresh.
  }
}

export function prefersDark(): boolean {
  return window.matchMedia(DARK_QUERY).matches;
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") return prefersDark() ? "dark" : "light";
  return preference;
}

/**
 * Estampa el tema resuelto en `<html data-theme>`. Nunca lo deja vacío: así el CSS
 * solo necesita `:root` y `[data-theme="dark"]`, sin media queries duplicadas.
 */
export function applyTheme(preference: ThemePreference): ResolvedTheme {
  const resolved = resolveTheme(preference);
  document.documentElement.dataset.theme = resolved;
  return resolved;
}

/** Avisa cuando cambia el tema del sistema. Devuelve la función para desuscribirse. */
export function watchSystemTheme(onChange: (isDark: boolean) => void): () => void {
  const media = window.matchMedia(DARK_QUERY);
  const listener = (event: MediaQueryListEvent) => onChange(event.matches);
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}
