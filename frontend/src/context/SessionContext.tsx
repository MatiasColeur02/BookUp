import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { clearToken, getToken, setToken, subscribe } from "../lib/session";
import type { User } from "../types";

interface Session {
  user: User | null;
  token: string | null;
  /** `true` mientras se resuelve la sesión guardada contra `GET /auth/me`. */
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  /** Refresca el `User` del contexto (después de editar el perfil, por ejemplo). */
  refresh: () => Promise<void>;
  isCustomer: boolean;
  isLibrarian: boolean;
  isSysadmin: boolean;
  /** Sede a cargo; solo la tiene un `librarian`. */
  myLibraryId: number | null;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken());
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => getToken() !== null);

  // El token puede cambiar desde afuera de React: el interceptor de 401 de `api.ts`
  // lo limpia cuando la API rechaza la sesión.
  useEffect(() => subscribe(setTokenState), []);

  useEffect(() => {
    if (token === null) {
      setUser(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    // Recuperar la sesión guardada sirve además para validar el token: si ya venció o
    // el usuario fue borrado, `/auth/me` da 401 y el interceptor lo limpia solo.
    api.auth
      .me()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.auth.login({ email, password });
    setToken(access_token);
    const me = await api.auth.me();
    setUser(me);
    setLoading(false);
    return me;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    if (getToken() === null) return;
    setUser(await api.auth.me());
  }, []);

  const value = useMemo<Session>(
    () => ({
      user,
      token,
      loading,
      login,
      logout,
      refresh,
      isCustomer: user?.role === "customer",
      isLibrarian: user?.role === "librarian",
      isSysadmin: user?.role === "sysadmin",
      myLibraryId: user?.library_id ?? null,
    }),
    [user, token, loading, login, logout, refresh]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error("useSession tiene que usarse dentro de <SessionProvider>");
  return session;
}
