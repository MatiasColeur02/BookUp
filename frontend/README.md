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
  context/ToastContext    estado de las notificaciones + hook useToast()
  hooks/                  hooks compartidos (useCopyDetails)
  lib/                    session (localStorage), errors, roles, isbn, reservations
  components/             pantallas y piezas de UI
  components/Toast.tsx    presentación de los toasts (lo único que sabe cómo se ven)
  components/admin/       gestión de catálogo, ejemplares (librarian/sysadmin)
```

Reglas de la casa:

- Solo `api.ts` hace `fetch`; solo `lib/session.ts` toca `localStorage`.
- Los componentes no arman URLs ni headers, y no manipulan el token directamente.
- Cada endpoint nuevo se agrega primero a `types.ts` y `api.ts`, con los códigos de
  error que declara el spec.

## Feedback al usuario: toasts y errores

La regla de dónde reporta cada cosa, para no duplicar el mismo mensaje en dos lugares:

| Qué pasó | Dónde se ve | Por qué |
|---|---|---|
| Una **acción** salió bien (reservar, cancelar, retirar, crear, borrar, subir portada) | Toast verde | Es efímero: la pantalla ya se recargó y muestra el nuevo estado |
| Una **acción** falló (409, 403, red) | Toast rojo | El error es sobre lo que acabás de apretar, no sobre lo que estás mirando |
| Éxito **parcial** (el libro se guardó pero la portada no subió) | Toast amarillo | Ni verde ni rojo: una parte quedó hecha |
| **Validación de formulario** (422 con la lista de campos, ISBN inválido, fecha pasada) | `ErrorBanner` inline | Hay que leerlo al lado del input que hay que corregir, y no se puede autocerrar |
| **La pantalla no cargó** (falla el GET del listado) | `ErrorBanner` inline | Si se fuera con el toast, quedaría una tabla vacía sin explicación |

Consecuencia práctica: un formulario (alta/edición de libro, sede, usuario, perfil)
confirma por toast y falla inline; una acción de fila (borrar, cancelar, marcar
retirada) hace las dos cosas por toast.

**Cómo se usa** — `useToast()` en cualquier componente:

```tsx
const toast = useToast();

toast.success("Reserva creada.");
// `error` acepta el error crudo de `api.ts` y lo traduce con `describeError`,
// con el mismo mapa de overrides por status que usa `ErrorBanner`.
toast.error(err, { 409: "Alguien reservó este ejemplar antes que vos." });
toast.warning("...");  toast.info("...");
```

**Cómo se rediseñan.** El estado (cola, ids, tope de 4 simultáneos, duración por
defecto) vive en `context/ToastContext.tsx` y no dibuja nada; el aspecto entero está en
`components/Toast.tsx` y en el bloque `Toasts` de `index.css`. Cambiar posición,
animación, colores o agregar una variante se hace en esos dos archivos, sin tocar
ninguna de las ~15 pantallas que los disparan. Los detalles: se apilan abajo a la
derecha, duran 5 s (`DEFAULT_TOAST_DURATION`, pisable por llamada; `duration: 0` no
autocierra), el timer se pausa con el mouse encima, y el viewport se monta con
`createPortal` en `document.body` con `z-index` por encima del modal.
