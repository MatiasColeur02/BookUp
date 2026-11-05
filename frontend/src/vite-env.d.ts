/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  /** `local` (default): `POST /auth/login`. `cognito`: la API del User Pool (`lib/auth.ts`). */
  readonly VITE_AUTH_MODE?: string;
  /** Solo con `VITE_AUTH_MODE=cognito`. */
  readonly VITE_COGNITO_REGION?: string;
  readonly VITE_COGNITO_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
