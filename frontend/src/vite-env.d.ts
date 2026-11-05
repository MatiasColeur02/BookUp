/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  /** `local` (default): `POST /auth/login`. `cognito`: Hosted UI + puente (`lib/auth.ts`). */
  readonly VITE_AUTH_MODE?: string;
  /** Solo con `VITE_AUTH_MODE=cognito`. */
  readonly VITE_COGNITO_DOMAIN?: string;
  readonly VITE_COGNITO_CLIENT_ID?: string;
  readonly VITE_AUTH_CALLBACK_URL?: string;
  readonly VITE_AUTH_SIGNED_OUT_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
