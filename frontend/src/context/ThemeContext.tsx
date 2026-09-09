import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  applyTheme,
  getStoredPreference,
  storePreference,
  watchSystemTheme,
  type ResolvedTheme,
  type ThemePreference,
} from "../lib/theme";

interface Theme {
  /** Lo que eligió la persona: `light`, `dark` o `system`. */
  preference: ThemePreference;
  /** Lo que se está mostrando: `system` ya resuelto contra el SO. */
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<Theme | null>(null);

/**
 * Tema de la app. Va por fuera de `SessionProvider`: el tema no depende de estar
 * logueado, aunque el selector viva en Mi perfil.
 *
 * El `data-theme` inicial ya lo estampa el script inline de `index.html` (para que no
 * haya flash blanco al recargar en oscuro); acá se vuelve a aplicar para cubrir el caso
 * de que ese script no haya corrido.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => getStoredPreference());
  const [resolved, setResolved] = useState<ResolvedTheme>(() => applyTheme(getStoredPreference()));

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    storePreference(next);
    setResolved(applyTheme(next));
  }, []);

  // Solo mientras la preferencia sea `system` importa lo que haga el SO.
  useEffect(() => {
    if (preference !== "system") return;
    return watchSystemTheme(() => setResolved(applyTheme("system")));
  }, [preference]);

  const value = useMemo<Theme>(
    () => ({ preference, resolved, setPreference }),
    [preference, resolved, setPreference]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme tiene que usarse dentro de un <ThemeProvider>");
  }
  return context;
}
