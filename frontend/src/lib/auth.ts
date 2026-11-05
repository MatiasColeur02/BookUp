/**
 * Ingreso con Cognito desde los formularios propios (`VITE_AUTH_MODE=cognito`).
 *
 * No hay Hosted UI ni redirects: el browser llama directo a la API del User Pool
 * (`cognito-idp.<region>.amazonaws.com`, HTTPS y con CORS abierto), con un app client
 * **público** —sin secret, que en el browser no se puede guardar— y el flujo
 * `USER_PASSWORD_AUTH`. La contraseña viaja a Cognito por TLS aunque el frontend se sirva
 * por HTTP desde el website de S3, y nunca pasa por nuestra API.
 *
 * Por qué no SRP (`USER_SRP_AUTH`, el flujo que no manda la contraseña): las librerías que lo
 * implementan usan `crypto.subtle`, que el browser solo ofrece en contextos seguros (HTTPS o
 * localhost), y en AWS Academy el frontend es HTTP.
 *
 * De la respuesta del login se guarda **solo el access token** (`lib/session.ts`), que es lo
 * que la API valida. El refresh token se descarta a propósito: en `localStorage` una XSS se lo
 * llevaría y la sesión duraría 30 días en vez de lo que dura el access token.
 *
 * Con `VITE_AUTH_MODE=local` (o sin definir) nada de esto se usa: el login es
 * `POST /auth/login` de la API, como siempre.
 */

export type AuthMode = "local" | "cognito";

export const AUTH_MODE: AuthMode = import.meta.env.VITE_AUTH_MODE === "cognito" ? "cognito" : "local";

export const isCognito = AUTH_MODE === "cognito";

interface CognitoConfig {
  endpoint: string;
  clientId: string;
}

let config: CognitoConfig | null = null;

/** Las `VITE_*` las hornea Vite en el build: si falta una, el build quedó mal configurado. */
function cognitoConfig(): CognitoConfig {
  if (config) return config;
  const env = import.meta.env;
  const missing = (
    [
      ["VITE_COGNITO_REGION", env.VITE_COGNITO_REGION],
      ["VITE_COGNITO_CLIENT_ID", env.VITE_COGNITO_CLIENT_ID],
    ] as const
  )
    .filter(([, value]) => !value)
    .map(([name]) => name);
  if (missing.length > 0) {
    throw new Error(`El ingreso no está configurado: falta ${missing.join(", ")}.`);
  }
  config = {
    endpoint: `https://cognito-idp.${env.VITE_COGNITO_REGION}.amazonaws.com/`,
    clientId: env.VITE_COGNITO_CLIENT_ID!,
  };
  return config;
}

/**
 * Un error de Cognito, con el mensaje ya traducido para la pantalla. `code` es el tipo de
 * excepción de Cognito sin prefijo (`NotAuthorizedException`, `CodeMismatchException`, …),
 * para que los formularios decidan el paso siguiente (p. ej. pedir el código de
 * confirmación). `ErrorBanner` muestra `message` tal cual (`describeError`).
 */
export class CognitoError extends Error {
  constructor(
    readonly code: string,
    message: string
  ) {
    super(message);
    this.name = "CognitoError";
  }
}

function describeCognitoError(code: string, raw: string): string {
  switch (code) {
    case "NotAuthorizedException":
      // El mismo código cubre credenciales incorrectas y el bloqueo por intentos fallidos.
      return /attempts exceeded/i.test(raw)
        ? "Demasiados intentos fallidos. Esperá unos minutos y volvé a probar."
        : "Email o contraseña incorrectos.";
    case "UserNotFoundException":
      // Con `prevent_user_existence_errors` no debería llegar, pero por las dudas no se
      // distingue de una contraseña incorrecta.
      return "Email o contraseña incorrectos.";
    case "UserNotConfirmedException":
      return "Todavía no confirmaste tu email.";
    case "PasswordResetRequiredException":
      return "Tenés que elegir una contraseña nueva. Usá «¿Olvidaste tu contraseña?».";
    case "UsernameExistsException":
      return "Ese email ya está registrado.";
    case "InvalidPasswordException":
      return "La contraseña no cumple la política: al menos 8 caracteres.";
    case "CodeMismatchException":
      return "El código no es correcto.";
    case "ExpiredCodeException":
      return "El código venció. Pedí uno nuevo.";
    case "LimitExceededException":
    case "TooManyRequestsException":
    case "TooManyFailedAttemptsException":
      return "Demasiados intentos. Esperá unos minutos y volvé a probar.";
    case "CodeDeliveryFailureException":
      return "No pudimos mandar el email con el código. Probá de nuevo más tarde.";
    case "InvalidParameterException":
      return "Revisá los datos enviados.";
    case "UserLambdaValidationException":
    case "UnexpectedLambdaException":
      return "No pudimos terminar de crear tu cuenta. Probá de nuevo en unos minutos.";
    default:
      return "No se pudo completar la operación. Probá de nuevo.";
  }
}

/** Una llamada a la API de Cognito (JSON 1.1 con `X-Amz-Target`, sin firma: client público). */
async function call<T>(action: string, body: Record<string, unknown>): Promise<T> {
  const { endpoint } = cognitoConfig();
  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": `AWSCognitoIdentityProviderService.${action}`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new CognitoError("NetworkError", "No se pudo conectar con el servicio de ingreso.");
  }

  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    // `__type` puede venir como `NotAuthorizedException` o con un prefijo `…#`.
    const code = String(payload.__type ?? "UnknownError").split("#").pop()!;
    const raw = String(payload.message ?? payload.Message ?? "");
    throw new CognitoError(code, describeCognitoError(code, raw));
  }
  return payload as T;
}

interface AuthenticationResult {
  AccessToken: string;
  ExpiresIn: number;
}

interface InitiateAuthResponse {
  AuthenticationResult?: AuthenticationResult;
  ChallengeName?: string;
  Session?: string;
}

/** El login pidió un paso más. Hoy el único que se maneja es la contraseña temporal. */
export interface NewPasswordChallenge {
  email: string;
  session: string;
}

export type SignInResult =
  | { kind: "signed-in"; accessToken: string }
  | { kind: "new-password-required"; challenge: NewPasswordChallenge };

function toSignInResult(email: string, response: InitiateAuthResponse): SignInResult {
  if (response.AuthenticationResult) {
    return { kind: "signed-in", accessToken: response.AuthenticationResult.AccessToken };
  }
  if (response.ChallengeName === "NEW_PASSWORD_REQUIRED" && response.Session) {
    // Personal dado de alta con `POST /users/staff`: la contraseña es temporal.
    return { kind: "new-password-required", challenge: { email, session: response.Session } };
  }
  throw new CognitoError(
    response.ChallengeName ?? "UnknownChallenge",
    "El ingreso pidió un paso que esta aplicación no soporta."
  );
}

export async function signIn(email: string, password: string): Promise<SignInResult> {
  const response = await call<InitiateAuthResponse>("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: cognitoConfig().clientId,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  });
  return toSignInResult(email, response);
}

/** Responde `NEW_PASSWORD_REQUIRED` con la contraseña definitiva. */
export async function completeNewPassword(
  challenge: NewPasswordChallenge,
  newPassword: string
): Promise<SignInResult> {
  const response = await call<InitiateAuthResponse>("RespondToAuthChallenge", {
    ChallengeName: "NEW_PASSWORD_REQUIRED",
    ClientId: cognitoConfig().clientId,
    Session: challenge.session,
    ChallengeResponses: { USERNAME: challenge.email, NEW_PASSWORD: newPassword },
  });
  return toSignInResult(challenge.email, response);
}

/**
 * Auto-registro de un lector. Cognito manda un código al email; recién al confirmarlo
 * (`confirmSignUp`) corre el trigger *Post Confirmation*, que crea el `User` (`customer`) en
 * DynamoDB.
 */
export async function signUp(email: string, password: string, name: string): Promise<void> {
  await call("SignUp", {
    ClientId: cognitoConfig().clientId,
    Username: email,
    Password: password,
    UserAttributes: [
      { Name: "email", Value: email },
      { Name: "name", Value: name },
    ],
  });
}

export async function confirmSignUp(email: string, code: string): Promise<void> {
  await call("ConfirmSignUp", {
    ClientId: cognitoConfig().clientId,
    Username: email,
    ConfirmationCode: code,
  });
}

export async function resendConfirmationCode(email: string): Promise<void> {
  await call("ResendConfirmationCode", { ClientId: cognitoConfig().clientId, Username: email });
}

/** Manda al email un código para elegir una contraseña nueva. */
export async function forgotPassword(email: string): Promise<void> {
  await call("ForgotPassword", { ClientId: cognitoConfig().clientId, Username: email });
}

export async function confirmForgotPassword(
  email: string,
  code: string,
  newPassword: string
): Promise<void> {
  await call("ConfirmForgotPassword", {
    ClientId: cognitoConfig().clientId,
    Username: email,
    ConfirmationCode: code,
    Password: newPassword,
  });
}

/** Cambio de contraseña con sesión abierta: pide la actual, como cualquier cambio de clave. */
export async function changePassword(
  accessToken: string,
  previousPassword: string,
  proposedPassword: string
): Promise<void> {
  await call("ChangePassword", {
    AccessToken: accessToken,
    PreviousPassword: previousPassword,
    ProposedPassword: proposedPassword,
  });
}
