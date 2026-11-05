import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api";
import {
  completeNewPassword as cognitoCompleteNewPassword,
  isCognito,
  signIn as cognitoSignIn,
  type NewPasswordChallenge,
  type SignInResult,
} from "../lib/auth";
import { clearToken, getToken, setToken, subscribe } from "../lib/session";
import type { User } from "../types";

/**
 * Cómo terminó un `login`. Con Cognito, el personal dado de alta por un sysadmin entra con
 * una contraseña temporal y el login pide elegir la definitiva antes de dar el token.
 */
export type LoginOutcome =
  | { kind: "signed-in"; user: User }
  | { kind: "new-password-required"; challenge: NewPasswordChallenge };

interface Session {
  user: User | null;
  token: string | null;
  /** `true` mientras se resuelve la sesión guardada contra `GET /auth/me`. */
  loading: boolean;
  /**
   * Ingresar con email y contraseña. Con `VITE_AUTH_MODE=local` va a `POST /auth/login`; con
   * `cognito`, directo al User Pool (`lib/auth.ts`), sin pasar por la API.
   */
  login: (email: string, password: string) => Promise<LoginOutcome>;
  /** Solo con Cognito: termina un login que pidió contraseña nueva. */
  completeNewPassword: (challenge: NewPasswordChallenge, newPassword: string) => Promise<User>;
  /**
   * Cierra la sesión: olvida el token. Con Cognito no hay cookie de Hosted UI que matar; el
   * access token sigue siendo válido hasta que vence (la API lo valida sin consultar a
   * Cognito), pero este browser ya no lo tiene.
   */
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
  // Token cuyo `User` ya trajimos: evita que el efecto de abajo repita el
  // `GET /auth/me` que `login` acaba de hacer.
  const resolvedToken = useRef<string | null>(null);

  // El token puede cambiar desde afuera de React: el interceptor de 401 de `api.ts`
  // lo limpia cuando la API rechaza la sesión.
  useEffect(() => subscribe(setTokenState), []);

  useEffect(() => {
    if (token === null) {
      resolvedToken.current = null;
      setUser(null);
      setLoading(false);
      return;
    }

    if (resolvedToken.current === token) {
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
        if (cancelled) return;
        resolvedToken.current = token;
        setUser(me);
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

  /** Guarda el token y trae su `User`, sin que el efecto de arriba repita el `/auth/me`. */
  const adoptToken = useCallback(async (accessToken: string) => {
    setToken(accessToken);
    const me = await api.auth.me();
    resolvedToken.current = accessToken;
    setUser(me);
    setLoading(false);
    return me;
  }, []);

  const finishCognito = useCallback(
    async (result: SignInResult): Promise<LoginOutcome> =>
      result.kind === "signed-in"
        ? { kind: "signed-in", user: await adoptToken(result.accessToken) }
        : result,
    [adoptToken]
  );

  const login = useCallback(
    async (email: string, password: string): Promise<LoginOutcome> => {
      if (isCognito) return finishCognito(await cognitoSignIn(email, password));
      const { access_token } = await api.auth.login({ email, password });
      return { kind: "signed-in", user: await adoptToken(access_token) };
    },
    [adoptToken, finishCognito]
  );

  const completeNewPassword = useCallback(
    async (challenge: NewPasswordChallenge, newPassword: string): Promise<User> => {
      const outcome = await finishCognito(await cognitoCompleteNewPassword(challenge, newPassword));
      if (outcome.kind !== "signed-in") throw new Error("El ingreso pidió otra contraseña nueva.");
      return outcome.user;
    },
    [finishCognito]
  );

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
      completeNewPassword,
      logout,
      refresh,
      isCustomer: user?.role === "customer",
      isLibrarian: user?.role === "librarian",
      isSysadmin: user?.role === "sysadmin",
      myLibraryId: user?.library_id ?? null,
    }),
    [user, token, loading, login, completeNewPassword, logout, refresh]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error("useSession tiene que usarse dentro de <SessionProvider>");
  return session;
}
