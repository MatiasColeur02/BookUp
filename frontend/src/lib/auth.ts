/**
 * Ingreso por la Hosted UI de Cognito (`VITE_AUTH_MODE=cognito`, `COGNITO_ROADMAP.md` §2 y §6).
 *
 * El flujo: `startLogin` guarda un `state` aleatorio en `sessionStorage` y navega a la Hosted
 * UI; Cognito vuelve al puente HTTPS (`auth-bridge/`), que canjea el code y redirige a la raíz
 * del frontend con `#access_token=…&expires_in=…&state=…`. `consumeAuthRedirect`, que corre
 * **antes** de montar React, compara el `state`, guarda el token con `setToken` y limpia el
 * fragmento. Un token cuyo `state` no es el que guardó esta pestaña se descarta: es la
 * defensa contra que alguien nos haga entrar con *su* cuenta (login CSRF) o contra un
 * `#access_token` viejo que vuelve desde el historial.
 *
 * Con `VITE_AUTH_MODE=local` (o sin definir) nada de esto se usa: el login es
 * `POST /auth/login` desde `LoginForm`, como siempre.
 *
 * Toca `sessionStorage` y no `localStorage`: el `state` pendiente vive solo en esta pestaña y
 * hasta la vuelta del login. El token sigue siendo cosa de `lib/session.ts`.
 */
import { setToken } from "./session";

export type AuthMode = "local" | "cognito";

export const AUTH_MODE: AuthMode = import.meta.env.VITE_AUTH_MODE === "cognito" ? "cognito" : "local";

export const isCognito = AUTH_MODE === "cognito";

const PENDING_KEY = "bookup.auth.pending";
const SCOPES = "openid email profile";

interface CognitoConfig {
  domain: string;
  clientId: string;
  callbackUrl: string;
  signedOutUrl: string;
}

interface Pending {
  state: string;
  returnTo: string;
}

/** Lo que pasó con el fragmento de la URL al arrancar, para que la UI lo cuente. */
export type AuthRedirectResult =
  | { kind: "none" }
  | { kind: "signed-in" }
  | { kind: "error"; error: string };

let config: CognitoConfig | null = null;

/** Las `VITE_*` las hornea Vite en el build: si falta una, el build quedó mal configurado. */
function cognitoConfig(): CognitoConfig {
  if (config) return config;
  const env = import.meta.env;
  const missing = (
    [
      ["VITE_COGNITO_DOMAIN", env.VITE_COGNITO_DOMAIN],
      ["VITE_COGNITO_CLIENT_ID", env.VITE_COGNITO_CLIENT_ID],
      ["VITE_AUTH_CALLBACK_URL", env.VITE_AUTH_CALLBACK_URL],
      ["VITE_AUTH_SIGNED_OUT_URL", env.VITE_AUTH_SIGNED_OUT_URL],
    ] as const
  )
    .filter(([, value]) => !value)
    .map(([name]) => name);
  if (missing.length > 0) {
    throw new Error(`VITE_AUTH_MODE=cognito requires ${missing.join(", ")}`);
  }
  // El dominio se acepta con o sin esquema, igual que en el puente.
  const domain = env.VITE_COGNITO_DOMAIN!.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  config = {
    domain: `https://${domain}`,
    clientId: env.VITE_COGNITO_CLIENT_ID!,
    callbackUrl: env.VITE_AUTH_CALLBACK_URL!,
    signedOutUrl: env.VITE_AUTH_SIGNED_OUT_URL!,
  };
  return config;
}

/** Solo rutas propias: `/panel`, nunca `//otro.sitio` ni `https://…`. */
function safeReturnTo(path: string | null | undefined): string {
  return path && path.startsWith("/") && !path.startsWith("//") ? path : "/";
}

function savePending(pending: Pending): void {
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
  } catch {
    // Sin sessionStorage el token que vuelva se va a descartar (no hay `state` contra qué
    // compararlo). Es lo correcto: sin esa comparación no hay forma de aceptarlo seguro.
  }
}

/** El pendiente, **consumido**: un `state` sirve para una sola vuelta. */
function takePending(): Pending | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    sessionStorage.removeItem(PENDING_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Pending>;
    return typeof parsed.state === "string"
      ? { state: parsed.state, returnTo: safeReturnTo(parsed.returnTo) }
      : null;
  } catch {
    return null;
  }
}

/**
 * 128 bits aleatorios en hex. No `crypto.randomUUID()`: solo existe en contextos seguros
 * (HTTPS o localhost), y en AWS Academy el frontend se sirve por HTTP desde el website de S3.
 * `getRandomValues` está disponible en HTTP y es el mismo generador criptográfico.
 */
function randomState(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Una pantalla de la Hosted UI con un `state` nuevo para esta vuelta. */
function hostedUiUrl(page: "oauth2/authorize" | "signup" | "forgotPassword", returnTo: string): string {
  const { domain, clientId, callbackUrl } = cognitoConfig();
  const state = randomState();
  savePending({ state, returnTo: safeReturnTo(returnTo) });
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: callbackUrl,
    scope: SCOPES,
    state,
  });
  return `${domain}/${page}?${params}`;
}

/** Ir a ingresar; después del login se vuelve a `returnTo`. */
export function startLogin(returnTo: string): void {
  window.location.assign(hostedUiUrl("oauth2/authorize", returnTo));
}

/** Ir a crear una cuenta (lector). Al confirmar el email, el trigger crea su usuario. */
export function startSignup(returnTo: string): void {
  window.location.assign(hostedUiUrl("signup", returnTo));
}

/**
 * Cambiar la contraseña: la Hosted UI manda un código al email y, al terminar, vuelve por el
 * callback como un login más. Por eso es una acción (genera `state`) y no un link fijo: un
 * link sin `state` traería un token que `consumeAuthRedirect` descartaría.
 */
export function startForgotPassword(returnTo: string): void {
  window.location.assign(hostedUiUrl("forgotPassword", returnTo));
}

/**
 * El `/logout` de Cognito: sin pasar por acá la cookie de la Hosted UI sigue viva y el
 * próximo «Ingresar» entra solo, con la misma cuenta (en una PC compartida, un problema).
 * Vuelve al frontend por el puente (`/signed-out`).
 */
export function logoutUrl(): string {
  const { domain, clientId, signedOutUrl } = cognitoConfig();
  const params = new URLSearchParams({ client_id: clientId, logout_uri: signedOutUrl });
  return `${domain}/logout?${params}`;
}

let redirectResult: AuthRedirectResult = { kind: "none" };

/**
 * Lee la vuelta del puente desde el fragmento de la URL. Va en `main.tsx` antes de
 * `createRoot`: así `SessionProvider` arranca con el token y el router con la ruta destino.
 */
export function consumeAuthRedirect(): AuthRedirectResult {
  if (!isCognito) return redirectResult;

  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get("access_token");
  const error = params.get("error");
  if (token === null && error === null) return redirectResult;

  const pending = takePending();
  const matches = pending !== null && params.get("state") === pending.state;
  let target = "/";

  if (!matches) {
    // Un token que esta pestaña no pidió no se guarda; un error tampoco vale de nada sin
    // contexto, pero se avisa igual.
    redirectResult = { kind: "error", error: token !== null ? "state_mismatch" : error! };
  } else if (token !== null) {
    setToken(token);
    target = pending.returnTo;
    redirectResult = { kind: "signed-in" };
  } else {
    target = pending.returnTo;
    redirectResult = { kind: "error", error: error! };
  }

  // Fuera de la barra de direcciones (y del historial): el token no puede quedar a la vista
  // ni volver con «atrás». `replaceState` y no `location`, para no recargar la página.
  window.history.replaceState(window.history.state, "", target);
  return redirectResult;
}

/** El resultado de `consumeAuthRedirect`, una sola vez (lo muestra `AuthRedirectNotice`). */
export function takeAuthRedirectResult(): AuthRedirectResult {
  const result = redirectResult;
  redirectResult = { kind: "none" };
  return result;
}

/** El mensaje de un `#error=` de la vuelta del login. */
export function describeAuthError(error: string): string {
  switch (error) {
    case "access_denied":
      return "Cancelaste el ingreso.";
    case "exchange_failed":
      return "No se pudo completar el ingreso. Probá de nuevo.";
    case "state_mismatch":
      return "Descartamos un ingreso que no se inició desde esta pestaña. Volvé a ingresar.";
    default:
      return "No se pudo ingresar. Probá de nuevo.";
  }
}
