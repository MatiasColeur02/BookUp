# Frontend BookUp

SPA en React 18 + TypeScript + Vite que consume la API de `../api`. El plan de trabajo
y las decisiones tomadas están en [`ROADMAP.md`](ROADMAP.md).

## Comandos

```bash
npm install
cp .env.example .env      # ajustar VITE_API_URL si la API no está en localhost:8000
npm run dev               # servidor de desarrollo en http://localhost:5173
npm run build             # tsc --noEmit + build de producción en dist/
npm run preview           # sirve dist/ para revisar el build
```

`npm run build` es la única verificación automática del proyecto: no hay tests ni
linter configurados. Corrélo antes de commitear — `tsc --noEmit` es lo que garantiza
que `src/types.ts` siga alineado con `api/openapi.yml`.

Con Docker Compose (desde la raíz del repo, levanta Postgres + API + frontend):

```bash
docker compose up --build
```

El contenedor corre `npm run dev`, así que **no** ejecuta `tsc`: los errores de tipo
solo aparecen si corrés `npm run build` a mano.

## Variables de entorno

| Variable | Default | Para qué |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Base de todas las llamadas a la API |

## Probar cada rol

Con la API levantada, `python -m app.seed` (desde `api/`) carga datos de ejemplo. Todos
los usuarios del seed comparten la password **`bookup123`**:

| Email | Rol | Qué ve |
|---|---|---|
| `ana@bookup.example` | `customer` | Catálogo, reservar, «Mis reservas», perfil |
| `central@bookup.example` | `librarian` (sede Central) | Además: panel de sede y gestión, acotados a su sede |
| `norte@bookup.example` | `librarian` (sede Norte) | Ídem, sobre la otra sede |
| `admin@bookup.example` | `sysadmin` | Todo, sin filtro de sede |

## Estructura

```
src/
  api.ts                  cliente HTTP: token, ApiError, un método por endpoint
  types.ts                contrato con la API (espeja api/openapi.yml)
  context/SessionContext  sesión: user, token, login/logout, helpers de rol
  hooks/                  hooks compartidos (useCopyDetails)
  lib/                    session (localStorage), errors, roles, isbn, reservations
  components/             pantallas y piezas de UI
  components/admin/       gestión de catálogo, ejemplares (librarian/sysadmin)
```

Reglas de la casa:

- Solo `api.ts` hace `fetch`; solo `lib/session.ts` toca `localStorage`.
- Los componentes no arman URLs ni headers, y no manipulan el token directamente.
- Cada endpoint nuevo se agrega primero a `types.ts` y `api.ts`, con los códigos de
  error que declara el spec.
