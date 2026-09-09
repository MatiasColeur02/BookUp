# CLAUDE.md — Rediseño visual del frontend

Especificación del diseño de la SPA. **Está implementada**: `src/index.css` tiene las cinco
capas de la sección 5 y las pantallas usan las primitivas de la sección 6. Este documento
sigue siendo la referencia — al agregar una pantalla o un estilo, valen las reglas de la
sección 10.

**Quedó pendiente** de lo que especifica el documento (nada de esto bloquea el diseño, y
está escrito acá para que no se pierda):

- **`aria-invalid` por campo** (§6.2): los formularios siguen mostrando el 422 solo en el
  banner. La regla CSS ya existe; falta que cada form lea `ApiError.fields` y marque el
  input correspondiente.
- **Borde del header al scrollear** (§7.1): el header sticky lleva el borde siempre, sin
  la clase `.is-scrolled`. Es una línea de CSS menos y un listener de scroll menos.
- **`.card-flush`** (§6.3): no se usó y no se escribió. Las tablas quedaron apoyadas
  directamente sobre el fondo, dentro de `.table-wrap`, sin tarjeta contenedora — que se
  ve mejor que la tarjeta-dentro-de-tarjeta que había antes.
- **Pantallas de listado como `.card`** (§6.3): quedaron como `.stack` (contenedor sin
  superficie), por la misma razón: el título va afuera y la tabla se enmarca sola.
- **Skeleton de la ficha del libro** (§6.10): el modal sigue diciendo "Consultando
  disponibilidad...". Los otros dos skeletons (grilla y tablas) sí están.
- **Verificación de contraste AA** (§8): los tokens están elegidos para cumplirlo pero no
  se midió con herramienta. Es lo primero a chequear en la próxima pasada.

Los otros dos documentos de `frontend/` siguen vigentes y no se pisan con este:

- [`README.md`](README.md) — comandos, estructura del código y la política de feedback
  (toasts vs. banners). Esa política **no cambia** acá; solo cambia cómo se ven.
- [`ROADMAP.md`](ROADMAP.md) — plan funcional contra `api/openapi.yml`. Este rediseño no
  agrega ni saca funcionalidad: ninguna pantalla cambia lo que hace.

## 0. Decisiones ya tomadas

Están cerradas y el resto del documento las asume:

| Decisión | Elección | Consecuencia |
|---|---|---|
| Dirección estética | **Editorial moderno (evolución)** | Se conserva el ADN de biblioteca: papel cálido, serif en títulos, terracota. Se moderniza densidad, jerarquía, sombras, radios, foco y estados. La app se tiene que seguir reconociendo. |
| Modo oscuro | **Sí, con selector manual en Mi perfil** | Hay que tocar React: `data-theme` en `<html>`, contexto de tema, persistencia y el toggle dentro de `ProfileView`. Ver sección 4. |
| Arquitectura CSS | **Un solo `index.css`, con capa de tokens arriba** | Sin dependencias nuevas, sin build extra. El archivo se reordena en 5 capas. |
| Alcance | **Aspecto + layout de navegación** | Se puede tocar `App.tsx` (header) y `admin/AdminLayout.tsx` (navegación de Gestión). El resto de los `.tsx` solo cambia clases, no estructura de datos ni lógica. |

**Fuera de alcance**: cambiar librerías (no entra Tailwind ni CSS-in-JS), agregar
dependencias de UI, tocar `api.ts` / `types.ts` / contextos que no sean el de tema, y
rediseñar pantallas enteras (las tablas siguen siendo tablas, la ficha sigue siendo un
modal).

---

## 1. Diagnóstico del CSS actual

`src/index.css` son 1472 líneas escritas por acumulación. No está mal hecho, pero tiene
cinco problemas concretos que el rediseño tiene que corregir **por diseño**, no de paso:

1. **No hay primitivas: hay ocho botones distintos.** `.tabs button` (l. 151), `.search-bar
   button` (l. 213), `.library-list button` (l. 803), `.form-card .actions button[type=submit]`
   (l. 894), `.confirm-button` (l. 1075), `.row-button` (l. 1094), `.session-link` (l. 983),
   `.load-more` (l. 439) y `.chip-remove` (l. 1369). Cada uno redefine padding, radio, peso y
   hover. Cambiar "cómo se ve un botón primario" hoy son nueve ediciones.
2. **Los inputs están copiados seis veces.** `.search-bar input`, `.form-card input/select`,
   `.form-card textarea`, `.inline-select select/input`, `.inline-input`, `.librarian-name
   input`: todos repiten `border: 1px solid var(--border); border-radius: 8px; font-family:
   var(--font-body)` y el mismo focus.
3. **El foco es inaccesible.** El patrón repetido es `outline: none; border-color:
   var(--accent)` (seis veces). Con teclado, en un `select` o un botón, eso es casi invisible.
   No hay una sola regla `:focus-visible` en todo el archivo.
4. **Hay colores fuera del sistema.** `body` hardcodea `#faf6ec` en el `radial-gradient`
   (l. 47) y `.chip-remove:hover` usa `rgba(133, 67, 31, 0.15)` (l. 1387) — el acento
   escrito a mano. Con dos temas, cada color suelto es un bug garantizado.
5. **Nombres que mienten.** `.librarian-panel` se usa como "tarjeta de página" en 8
   archivos, la mayoría de los cuales no son el panel del bibliotecario (`MyReservationsView`,
   `BooksAdmin`, `UsersAdmin`, `MaintenanceView`, …). `.status-pending` / `.status-confirmed`
   / `.status-fulfilled` no son estados del dominio (que son *reservada, retirada, devuelta,
   cancelada, vencida*). Y `.librarian-name` (l. 1018-1040, 23 líneas) **está muerto**: cero usos
   en `.tsx`.

Además, dos limitaciones visuales del diseño actual que el rediseño sí ataca:

- **Densidad plana.** Todo vive a la misma distancia: mismas sombras, mismo radio (8-14px),
  mismo peso. Con la grilla de portadas nueva, el catálogo pide una jerarquía de elevación.
- **Ancho corto.** `.app { max-width: 1000px }` aprieta las tablas de gestión (la de
  ejemplares tiene 6 columnas) y limita la grilla de portadas a 5 columnas.

---

## 2. Dirección: editorial moderno

La referencia mental es una **revista de tipografía cuidada**, no un dashboard. Seis
principios, cada uno con su consecuencia práctica:

1. **El papel es el fondo, la tarjeta es blanca.** Hoy el fondo es crema saturado
   (`#f5efe2`) y las tarjetas son casi del mismo color (`#fffdf8`): no se separan. El
   rediseño baja la saturación del fondo y sube el contraste de la tarjeta a blanco puro.
2. **La portada manda.** En el catálogo, el color lo ponen los libros. La UI alrededor es
   neutra y cálida; el acento se reserva para lo accionable.
3. **Jerarquía por tipografía y espacio, no por cajas.** Menos bordes, menos fondos grises.
   Donde hoy hay un recuadro para separar, va aire.
4. **Serif solo en títulos de contenido.** Fraunces para nombres de libros, títulos de
   pantalla y el wordmark. Nunca en botones, labels, tablas ni datos.
5. **Elevación con intención.** Tres niveles y no más: plano (contenido), tarjeta
   (`shadow-sm`), flotante (modal/toast, `shadow-lg`). Una sombra significa "esto está por
   encima", no "esto es lindo".
6. **Movimiento corto o nada.** 120-180 ms, solo en `opacity`, `transform` y `background`.
   Nunca animar `width`, `height` ni `top`.

---

## 3. Capa 0 — Tokens

Reemplaza el `:root` actual (l. 1-37). Dos niveles: **paleta cruda** (no se usa en las
reglas, solo la consumen los semánticos) y **semánticos** (lo único que se usa). Dark mode
redefine únicamente los semánticos.

### 3.1 Paleta cruda

```css
:root {
  /* Arena: el papel. Reemplaza al crema saturado actual. */
  --sand-50:  #faf8f5;
  --sand-100: #f4f0e9;
  --sand-200: #eae4da;
  --sand-300: #dcd4c6;
  --sand-400: #c4b9a6;

  /* Terracota: el acento de marca (hoy #85431f). */
  --clay-50:  #f9efe7;
  --clay-100: #f1dccc;
  --clay-200: #e0b795;
  --clay-500: #7c3f1d;
  --clay-600: #653116;
  --clay-700: #4f2510;
  --clay-300: #c98d5c;   /* acento sobre superficies oscuras */

  /* Tinta: textos. Neutro cálido, no gris puro. */
  --ink-900: #1c1917;
  --ink-700: #44403c;
  --ink-500: #78716c;
  --ink-400: #a8a29e;

  /* Tinta oscura: superficies del tema dark, cálidas (no azuladas). */
  --night-900: #14120f;
  --night-800: #1c1a16;
  --night-700: #24211b;
  --night-600: #322d25;
  --night-500: #453e33;

  /* Estados. Cada uno tiene versión clara (sobre papel) y oscura (sobre night). */
  --green-500: #2f6b45;  --green-300: #6ec08d;  --green-50: #e6f0e8;  --green-900: #16281d;
  --amber-500: #9a6412;  --amber-300: #e0a548;  --amber-50: #faeed6;  --amber-900: #2e2214;
  --red-500:   #a3311c;  --red-300:   #ef8b73;  --red-50:   #fbe6e0;  --red-900:   #331a14;
  --slate-500: #4b5563;  --slate-300: #9aa4b2;  --slate-50: #eceef1;  --slate-900: #21262e;
}
```

### 3.2 Semánticos (tema claro)

```css
:root {
  color-scheme: light;

  /* Superficies */
  --bg:              var(--sand-50);
  --bg-elevated:     #ffffff;      /* tarjetas, modal, toast */
  --bg-subtle:       var(--sand-100);   /* thead, segmented, zonas de descanso */
  --bg-hover:        var(--sand-100);   /* hover de filas y botones fantasma */
  --border:          var(--sand-200);
  --border-strong:   var(--sand-300);   /* separadores que sí tienen que verse */

  /* Texto */
  --text:            var(--ink-900);
  --text-muted:      var(--ink-500);
  --text-faint:      var(--ink-400);    /* placeholders, metadatos terciarios */
  --text-on-accent:  #ffffff;

  /* Acento */
  --accent:          var(--clay-500);
  --accent-hover:    var(--clay-600);
  --accent-active:   var(--clay-700);
  --accent-soft:     var(--clay-50);    /* fondo de chips, badges, scope-note */
  --accent-border:   var(--clay-100);

  /* Estados semánticos */
  --success: var(--green-500); --success-soft: var(--green-50);
  --warning: var(--amber-500); --warning-soft: var(--amber-50);
  --danger:  var(--red-500);   --danger-soft:  var(--red-50);
  --neutral: var(--slate-500); --neutral-soft: var(--slate-50);

  /* Foco: un anillo, no un borde de color */
  --ring: 0 0 0 3px rgb(124 63 29 / 0.25);
  --ring-danger: 0 0 0 3px rgb(163 49 28 / 0.25);
}
```

### 3.3 Semánticos (tema oscuro)

Solo se redefinen los semánticos. **Ninguna otra regla del archivo se duplica para dark**;
si una regla necesita un `[data-theme="dark"]` propio, es que está usando un color suelto y
hay que tokenizarlo.

```css
[data-theme="dark"] {
  color-scheme: dark;

  --bg:            var(--night-900);
  --bg-elevated:   var(--night-800);
  --bg-subtle:     var(--night-700);
  --bg-hover:      var(--night-700);
  --border:        var(--night-600);
  --border-strong: var(--night-500);

  --text:           #f2ede5;
  --text-muted:     #a9a196;
  --text-faint:     #7d7568;
  --text-on-accent: var(--night-900);   /* el acento se aclara: el texto se oscurece */

  --accent:        var(--clay-300);
  --accent-hover:  #d89b6d;
  --accent-active: var(--clay-200);
  --accent-soft:   #33241a;
  --accent-border: #4a3527;

  --success: var(--green-300); --success-soft: var(--green-900);
  --warning: var(--amber-300); --warning-soft: var(--amber-900);
  --danger:  var(--red-300);   --danger-soft:  var(--red-900);
  --neutral: var(--slate-300); --neutral-soft: var(--slate-900);

  --ring: 0 0 0 3px rgb(201 141 92 / 0.35);
  --ring-danger: 0 0 0 3px rgb(239 139 115 / 0.30);
}
```

**Regla no negociable**: en dark, `--text-on-accent` es **oscuro**, porque el acento pasa a
ser claro. Todo lo que hoy escribe `color: var(--accent-contrast)` sobre fondo `--accent`
tiene que usar `--text-on-accent` para que funcione en los dos temas.

### 3.4 Tipografía

```css
:root {
  --font-display: "Fraunces", "Iowan Old Style", Georgia, serif;
  --font-body: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-wordmark: "Quicksand", var(--font-display);

  /* Escala. Los dos títulos grandes son fluidos: no hay saltos en el breakpoint. */
  --text-2xs:  0.6875rem;  /* 11px — solo mayúsculas de th y eyebrow */
  --text-xs:   0.75rem;    /* 12px — hints, metadatos */
  --text-sm:   0.8125rem;  /* 13px — labels, botones de fila, badges */
  --text-base: 0.9375rem;  /* 15px — cuerpo, celdas de tabla, inputs */
  --text-md:   1.0625rem;  /* 17px — títulos de tarjeta */
  --text-lg:   clamp(1.25rem, 1.1rem + 0.6vw, 1.5rem);   /* h2 de pantalla */
  --text-xl:   clamp(1.6rem, 1.3rem + 1.2vw, 2.1rem);    /* título de la ficha del libro */

  --leading-tight: 1.2;   /* títulos */
  --leading-snug: 1.4;    /* UI */
  --leading-normal: 1.6;  /* sinopsis y textos largos */

  --tracking-tight: -0.015em;  /* títulos grandes */
  --tracking-wide: 0.07em;     /* mayúsculas chicas */
}
```

Reglas de uso:

- `--font-display` **solo** en: wordmark, `h1`/`h2` de pantalla, título de la ficha del
  libro, título de libro en la grilla y en el placeholder de portada. En ningún otro lado.
- El peso de Fraunces es 600 para títulos y 700 para el wordmark. No usar 500 (se lava).
- Los números de tablas y fechas van con `font-variant-numeric: tabular-nums`. Es una línea
  en `td` y arregla que las columnas de fechas bailen.
- Nada por debajo de `--text-xs` (12px) salvo `--text-2xs`, y ese **solo** en mayúsculas con
  `--tracking-wide` (encabezados de tabla y `.eyebrow`).

### 3.5 Espaciado, radios, sombras, motion, capas

```css
:root {
  /* Escala de 4px. Prohibido escribir rem sueltos en padding/margin/gap. */
  --space-1: 0.25rem;  --space-2: 0.5rem;   --space-3: 0.75rem;  --space-4: 1rem;
  --space-5: 1.25rem;  --space-6: 1.5rem;   --space-8: 2rem;     --space-10: 2.5rem;
  --space-12: 3rem;    --space-16: 4rem;

  /* Radios: la escala actual (8/10/12/14/999) se ordena en cinco pasos. */
  --radius-sm: 8px;    /* inputs, botones chicos, badges cuadrados */
  --radius-md: 12px;   /* botones, celdas internas, portada */
  --radius-lg: 16px;   /* tarjetas, tabla, modal */
  --radius-xl: 24px;   /* contenedores grandes (hero de la ficha) */
  --radius-full: 999px;

  /* Sombras cálidas y en dos capas: una de contacto y una de ambiente. */
  --shadow-xs: 0 1px 2px rgb(28 25 23 / 0.05);
  --shadow-sm: 0 1px 2px rgb(28 25 23 / 0.05), 0 2px 6px -2px rgb(28 25 23 / 0.06);
  --shadow-md: 0 2px 4px -2px rgb(28 25 23 / 0.06), 0 10px 20px -6px rgb(28 25 23 / 0.10);
  --shadow-lg: 0 4px 8px -4px rgb(28 25 23 / 0.08), 0 24px 48px -12px rgb(28 25 23 / 0.18);

  --dur-fast: 120ms;
  --dur-base: 180ms;
  --dur-slow: 260ms;
  --ease-out: cubic-bezier(0.2, 0.8, 0.2, 1);

  --z-header: 10;
  --z-sticky: 20;
  --z-backdrop: 50;
  --z-modal: 51;
  --z-toast: 60;

  --container: 1120px;         /* hoy 1000px */
  --container-narrow: 30rem;   /* auth y perfil */
  --header-height: 4.5rem;
}

[data-theme="dark"] {
  /* En oscuro la sombra sola no separa: se apoya en el borde y sube opacidad. */
  --shadow-xs: 0 1px 2px rgb(0 0 0 / 0.30);
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.35), 0 2px 6px -2px rgb(0 0 0 / 0.30);
  --shadow-md: 0 2px 4px -2px rgb(0 0 0 / 0.40), 0 10px 20px -6px rgb(0 0 0 / 0.45);
  --shadow-lg: 0 4px 8px -4px rgb(0 0 0 / 0.45), 0 24px 48px -12px rgb(0 0 0 / 0.60);
}
```

### 3.6 Migración de los tokens viejos

Todos los tokens actuales desaparecen. Antes de borrar el `:root` viejo, hacer este
reemplazo global (son ~400 usos, `sed` alcanza, pero revisar los casos marcados):

| Token viejo | Token nuevo | Nota |
|---|---|---|
| `--bg` | `--bg` | Cambia el valor, no el nombre |
| `--surface` | `--bg-elevated` | |
| `--surface-muted` | `--bg-subtle` | Revisar caso por caso: en algunos usos era *hover* → `--bg-hover` |
| `--border` | `--border` | Cambia el valor |
| `--text` | `--text` | |
| `--muted` | `--text-muted` | |
| `--accent`, `--accent-hover` | igual | Cambia el valor |
| `--accent-soft` | `--accent-soft` | |
| `--accent-contrast` | `--text-on-accent` | **Crítico para dark** |
| `--shadow-sm`, `--shadow-md` | igual | Cambian los valores |
| `--font-*` | igual | |
| `--logo-terracotta/amber/ink` | se quedan | Son del logo, no del tema. En dark el logo no cambia. |

---

## 4. Modo oscuro: mecánica

El selector vive en **Mi perfil**, como se decidió. Implementación exacta:

### 4.1 Estado y persistencia

Tres valores posibles: `"light"`, `"dark"`, `"system"` (default). Es importante que exista
`"system"`: sin sesión no hay Mi perfil, y un visitante con el SO en oscuro tiene que ver la
app en oscuro igual.

- **`src/lib/theme.ts`** (nuevo, hermano de `lib/session.ts`): lee y escribe
  `localStorage["bookup:theme"]`, y expone `applyTheme(preference)` que resuelve `"system"`
  contra `matchMedia("(prefers-color-scheme: dark)")` y estampa
  `document.documentElement.dataset.theme` con `"light"` o `"dark"`. Nunca deja `data-theme`
  vacío: así el CSS solo necesita `:root` y `[data-theme="dark"]`.
- **`src/context/ThemeContext.tsx`** (nuevo): `{ preference, resolved, setPreference }`.
  Suscribe el `matchMedia` mientras la preferencia sea `"system"` y desuscribe si no.
- **`main.tsx`**: `<ThemeProvider>` **afuera** de `<SessionProvider>` — el tema no depende de
  la sesión.
- **`index.html`**: script inline en el `<head>`, antes de los estilos, que lee el
  `localStorage` y estampa `data-theme` sincrónicamente. Sin esto hay flash blanco en cada
  recarga con tema oscuro. Son 4 líneas y tienen que estar inline, no en un módulo.

### 4.2 El control en Mi perfil

En `ProfileView`, tarjeta nueva **"Apariencia"** entre la tarjeta de perfil y la zona de
peligro (el orden importa: la zona roja siempre va última). Un `.segmented` de tres opciones
—Claro / Auto / Oscuro— con el patrón `role="radiogroup"`, no un checkbox: son tres estados,
no dos. Guardar es inmediato, sin botón, y **no** dispara toast (el cambio ya es su propio
feedback).

### 4.3 Reglas para que dark no se rompa

1. Ninguna regla del archivo puede tener un color literal. Cero `#hex`, cero `rgb()` fuera de
   la capa de tokens. Las dos excepciones actuales (`body` background-image, `.chip-remove:hover`)
   se tokenizan.
2. Ninguna regla nueva puede llevar `[data-theme="dark"]`. Si hace falta, es señal de que
   falta un token.
3. Las portadas y el logo **no** se filtran ni se invierten en dark. Sí lleva la portada un
   `box-shadow` más marcado y `border-color: var(--border)` para separarse del fondo.
4. Las imágenes con fondo blanco (portadas escaneadas) van con
   `background: var(--bg-subtle)` para que el hueco mientras carga no sea un rectángulo
   blanco brillante.

---

## 5. Nueva estructura de `index.css`

Mismo archivo, cinco capas, en este orden y con estos comentarios de sección. El orden
importa: es lo que hace que las utilidades ganen sin `!important`.

```
/* ============ 1. TOKENS ============ */      ~140 líneas   sección 3 completa
/* ============ 2. BASE ============ */         ~60 líneas   reset, body, tipografía base,
                                                             :focus-visible global, .app
/* ============ 3. PRIMITIVAS ============ */  ~420 líneas   sección 6: .btn .field .card
                                                             .segmented .badge .chip .callout
                                                             .table .modal .toast .skeleton
/* ============ 4. COMPONENTES ============ */ ~600 líneas   sección 7, una subsección por
                                                             pantalla, en el orden en que el
                                                             usuario las encuentra
/* ============ 5. UTILIDADES ============ */   ~60 líneas   .muted .empty .visually-hidden
                                                             .stack .row
```

Dentro de la capa 4, el orden de subsecciones es: Header y navegación · Catálogo · Ficha del
libro · Reservas · Panel bibliotecario · Gestión · Perfil y auth · Sedes.

Una regla de la capa 4 **nunca** redefine padding/color/radio de una primitiva. Si un botón
necesita ser distinto dentro de una pantalla, es una variante nueva en la capa 3, no un
`.mi-pantalla .btn { padding: … }`.

---

## 6. Primitivas

### 6.1 `.btn` — reemplaza los ocho botones actuales

Estructura: `.btn` (base) + una variante + un tamaño opcional.

| Variante | Uso | Aspecto |
|---|---|---|
| `.btn-primary` | La acción principal de la pantalla o del formulario. **Una sola por vista.** | Fondo `--accent`, texto `--text-on-accent` |
| `.btn-secondary` | Acciones de fila, "Cancelar" de un form, "Cargar más" | Fondo `--bg-elevated`, borde `--border`, texto `--text` |
| `.btn-ghost` | Terciaria: cerrar, limpiar, volver | Sin fondo ni borde; hover `--bg-hover` |
| `.btn-danger` | Eliminar, dar de baja | Texto `--danger`, borde `--border`; en hover fondo `--danger-soft` y borde `--danger` |
| `.btn-success` | Confirmar un movimiento físico: retirada, devolución | Fondo `--success`, texto `--text-on-accent` |

Tamaños: `.btn-sm` (altura 32px, `--text-sm`) para acciones dentro de tablas; base (38px,
`--text-base`); `.btn-lg` (46px) solo para el submit de login/registro.

Especificación de la base:

- `display: inline-flex; align-items: center; gap: var(--space-2);` — así el `<CheckIcon/>`
  que ya usan `.confirm-button` y los toasts entra sin reglas extra.
- `border-radius: var(--radius-md)`, `font-weight: 550`, `white-space: nowrap`.
- `transition: background-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out)`.
- `:hover` no mueve nada (el `translateY` queda solo para las portadas). `:active { transform: translateY(1px) }`.
- `:focus-visible { outline: none; box-shadow: var(--ring) }` — y `--ring-danger` en `.btn-danger`.
- `:disabled { opacity: 0.55; cursor: not-allowed }` y **sin** hover.
- Estado ocupado: `.is-busy` con `cursor: progress` y opacidad. Hoy el patrón es cambiar el
  texto a "Guardando…"; eso se mantiene, la clase solo agrega el cursor.

**Qué reemplaza** (borrar estas reglas y poner clases en los `.tsx`):

| Regla actual | Va a |
|---|---|
| `.search-bar button` (l. 213) | `.btn .btn-primary` |
| `.library-list button` (l. 803) | `.btn .btn-primary .btn-sm` |
| `.form-card .actions button[type=submit]` (l. 894) | `.btn .btn-primary` |
| `.form-card .actions button[type=button]` (l. 905) | `.btn .btn-secondary` |
| `.confirm-button` (l. 1075) | `.btn .btn-success .btn-sm` |
| `.row-button` (l. 1094) | `.btn .btn-secondary .btn-sm` |
| `.row-button.danger` (l. 1109) | `.btn .btn-danger .btn-sm` |
| `.danger-button` (l. 946) | `.btn .btn-danger` |
| `.load-more` (l. 439) | `.btn .btn-secondary` |
| `.session-link` / `.session-link.primary` (l. 983) | `.btn .btn-ghost` / `.btn .btn-primary` |
| `.modal-close`, `.toast-close` | `.btn .btn-ghost .btn-icon` (variante cuadrada, 32×32) |

Archivos `.tsx` a tocar: `SearchBar`, `BookAvailabilityView`, `LibrarianPanel`,
`ReservationManageModal`, `MyReservationsView`, `CatalogView`, `Modal`, `Toast`,
`ProfileView`, `App`, y los seis de `admin/`. Es solo cambiar el `className`.

### 6.2 `.field` — reemplaza los seis inputs

Un bloque `<label class="field">` con: texto del label, control, y opcionalmente
`.field-hint` o `.field-error`.

- El label es `--text-sm`, `--text-muted`, `font-weight: 550`, `margin-bottom: var(--space-1)`.
- El control (`input, select, textarea`) comparte una sola regla: `padding: 0.55rem 0.7rem`,
  `border-radius: var(--radius-sm)`, `border: 1px solid var(--border)`,
  `background: var(--bg-elevated)`, `font: inherit`, `font-size: var(--text-base)`,
  `color: var(--text)`, y **altura mínima 40px** (hoy quedan en ~36px; en mobile es poco).
- `:focus-visible` → `border-color: var(--accent); box-shadow: var(--ring)`. Se elimina el
  patrón `outline: none` a secas.
- `:disabled` → `background: var(--bg-subtle); color: var(--text-muted)`.
- `[aria-invalid="true"]` → `border-color: var(--danger)` + `--ring-danger`. **Nuevo**: hoy
  un campo rechazado por el 422 no se marca, solo aparece el banner arriba. Al implementarlo,
  `ErrorBanner` sigue igual; lo que se agrega es el `aria-invalid` en los inputs que el 422
  nombra (`ApiError.fields`).
- Variante `.field-inline` (label y control en fila) para los filtros: reemplaza
  `.inline-select` (l. 1158).
- `.inline-input` (l. 1254, edición dentro de la tabla de autores/géneros) pasa a
  `.field-control .field-control-sm`.

### 6.3 `.card`

Reemplaza el grupo `.catalog-detail, .availability, .reservation-form, .form-card,
.librarian-panel` (l. 700).

- `background: var(--bg-elevated)`, `border: 1px solid var(--border)`,
  `border-radius: var(--radius-lg)`, `padding: var(--space-6)`, `box-shadow: var(--shadow-sm)`.
- Variantes: `.card-flush` (sin padding, para envolver una tabla), `.card-subtle`
  (`background: var(--bg-subtle)`, sin sombra — reemplaza el fondo gris de
  `.reservation-form`), `.card-danger` (borde `--danger`, para la zona de peligro del perfil).
- Dentro de un modal la tarjeta pierde borde y sombra (el marco lo pone el diálogo). Eso ya
  existe hoy como `.modal .form-card` / `.modal .catalog-detail`: se generaliza a
  `.modal .card { border: none; box-shadow: none; }`.
- **Renombrar `.librarian-panel` → `.card` + `.page-header`** en los 8 archivos que la usan.
  Es el cambio de nombre más importante del rediseño: hoy la clase miente sobre qué es.

### 6.4 `.segmented`

`.tabs` (l. 142) y `.filters` (l. 1124) son el mismo control con dos nombres: píldora
contenedora + botones, uno activo. Se unifican.

- Contenedor: `background: var(--bg-subtle)`, `border: 1px solid var(--border)`,
  `border-radius: var(--radius-full)`, `padding: var(--space-1)`, `gap: var(--space-1)`,
  y `overflow-x: auto` con `scrollbar-width: none` para que en mobile se pueda arrastrar en
  vez de romper el header.
- Ítem activo: fondo `--bg-elevated` + `--shadow-xs` + texto `--text` — **no** fondo acento.
  Hoy el activo es un bloque terracota, que en una barra de 6 pestañas pesa demasiado y pelea
  con el botón primario de la pantalla. El acento queda para acciones, no para navegación.
  (Excepción: los filtros de reservas, donde el activo sí lleva `color: var(--accent)`.)
- Tamaños: base para la nav principal, `.segmented-sm` para los filtros de listado.

### 6.5 `.badge` y `.chip`

- `.badge`: unifica `.badge` (l. 791), `.role-chip` (l. 974) y `.status-badge` (l. 1397).
  Base: `--radius-full`, `--text-xs`, `font-weight: 600`, `padding: 0.15rem 0.55rem`,
  `border: 1px solid transparent`. Variantes de color: `.badge-accent`, `.badge-success`,
  `.badge-warning`, `.badge-danger`, `.badge-neutral` (fondo `*-soft`, texto el color).
- **Renombrar los estados de reserva** en `ReservationStatusBadge.tsx` para que digan lo que
  son: `status-pending → badge-warning`, `status-confirmed → badge-success`,
  `status-cancelled → badge-danger`, `status-fulfilled → badge-neutral`. El mapa de labels no
  se toca.
- El ISBN, que hoy usa `.badge` acento, pasa a `.badge-neutral` con
  `font-variant-numeric: tabular-nums`: es un dato, no un estado.
- `.chip` (ChipSelect) se queda con su forma actual pero toma el fondo `--accent-soft` y
  borde `--accent-border`, y el `.chip-remove:hover` usa
  `background: color-mix(in oklab, var(--accent) 15%, transparent)` en lugar del `rgba()`
  hardcodeado.

### 6.6 `.callout` — reemplaza `.error`, `.success`, `.api-status`, `.scope-note`

Cuatro reglas con la misma forma (fondo suave + texto de color + radio 8px). Se unifican en
`.callout` + variante, con un borde izquierdo de 3px del color del estado y `--radius-md`.
`ErrorBanner` pasa a `.callout .callout-danger`, `ApiStatus` a `.callout .callout-warning`,
la nota de alcance del perfil a `.callout .callout-accent`.

### 6.7 `.table`

- Envoltorio `.table-wrap`: `border-radius: var(--radius-lg)`, `overflow: auto` (hoy es
  `hidden`, que en mobile **corta** las tablas de 6 columnas en vez de dejarlas scrollear) y
  `-webkit-overflow-scrolling: touch`.
- `th`: `background: var(--bg-subtle)`, `--text-2xs`, mayúsculas, `--tracking-wide`,
  `position: sticky; top: 0; z-index: var(--z-sticky)` — con listados de 190 reservas, el
  encabezado pegajoso es la mejora más útil de toda la pantalla.
- `td`: `--text-base`, `padding: var(--space-3) var(--space-4)`,
  `border-top: 1px solid var(--border)`, `font-variant-numeric: tabular-nums`.
- Hover de fila: `background: var(--bg-hover)` (se mantiene), con `transition` corta.
- Última columna (acciones): `text-align: right; width: 1%; white-space: nowrap`.
- En `max-width: 720px`, la tabla no se convierte en cards (eso sería rediseño de pantalla,
  fuera de alcance): scrollea horizontal, con una sombra de borde que indique que hay más.

### 6.8 `.modal`

Se conserva la mecánica de `Modal.tsx` (portal, Escape, click en el fondo, scroll lock). Solo
cambia el aspecto:

- Backdrop: `background: rgb(28 25 23 / 0.45)` + `backdrop-filter: blur(3px)`; en dark
  `rgb(0 0 0 / 0.6)`. Ambos como token (`--backdrop`).
- Panel: `--radius-lg`, `--shadow-lg`, `border: 1px solid var(--border)` (en dark el borde es
  lo que lo separa del fondo), ancho `min(620px, 100%)`.
- **Entrada animada**: `opacity` + `translateY(8px)` en 180 ms, anulada por
  `prefers-reduced-motion`. Hoy aparece de golpe.
- Alineación: `align-items: flex-start` con `padding-block: 10vh` en desktop; en mobile
  (`max-width: 560px`) el modal se ancla abajo y ocupa el ancho completo, con las esquinas
  inferiores a 0 — el gesto de cerrar queda al alcance del pulgar.

### 6.9 `.toast`

Se conserva todo el comportamiento (posición abajo a la derecha, 5 s, pausa al hover, portal,
`role`). Cambios visuales: `--radius-lg`, `--shadow-lg`, borde izquierdo de 3px con el color
del estado (ya es así), y el ícono en un círculo de 22px con fondo `*-soft`. Agregar salida
animada además de la entrada, y en mobile pasar a ancho completo abajo (ya está).

### 6.10 `.skeleton` (nuevo)

Hoy toda la carga dice "Cargando catálogo…" en texto. Con la grilla de portadas eso produce
un salto grande. Se agrega un bloque de esqueleto: `background: var(--bg-subtle)` con un
barrido de `linear-gradient` animado en 1.4 s, `--radius-md`, y una animación desactivada por
`prefers-reduced-motion` (queda el color plano). Se usa en tres lugares: grilla del catálogo
(12 rectángulos con la proporción 2/3), tablas (5 filas) y la ficha del libro.

---

## 7. Pantalla por pantalla

### 7.1 Header y navegación (`App.tsx`, capa 4)

Problemas actuales: el header apila marca + 6 pestañas + sesión en una fila que se rompe en
notebooks; y las pestañas activas en terracota compiten con los botones de acción.

- `.app` pasa a `max-width: var(--container)` (1120px) con `padding-inline: var(--space-6)`.
- El header se vuelve **sticky**: `position: sticky; top: 0; z-index: var(--z-header)`,
  `background: color-mix(in oklab, var(--bg) 85%, transparent)` + `backdrop-filter: blur(8px)`,
  y `border-bottom: 1px solid var(--border)` que solo aparece al scrollear (clase
  `.is-scrolled` puesta desde `App.tsx` con un listener, o con `animation-timeline: scroll()`
  donde esté soportado y el borde fijo como fallback).
- Layout en dos filas dentro del header: fila 1 marca + accesos de sesión, fila 2 la
  navegación. En ≥900px, una sola fila con la navegación centrada.
- La navegación usa `.segmented` con el activo en superficie elevada (ver 6.4).
- El wordmark sube a `--text-md` y la tagline se oculta por debajo de 700px.

### 7.2 Gestión: navegación lateral (`admin/AdminLayout.tsx`)

Es el cambio de layout que habilita el alcance elegido. Hoy `AdminLayout` repite `.tabs` con
7 secciones, que en mobile desborda y en desktop compite con la nav principal.

- En ≥900px: grilla de dos columnas, `grid-template-columns: 200px minmax(0, 1fr)` con
  `gap: var(--space-8)`. La columna izquierda es una lista vertical de secciones, sticky bajo
  el header, con el ítem activo marcado por una barra de 3px del color acento a la izquierda y
  fondo `--bg-subtle` (no fondo acento: mismo criterio que 6.4).
- Por debajo de 900px vuelve al `.segmented` horizontal scrolleable actual.
- Cada sección lleva su ícono (hoy no hay: hay que sumar 7 íconos a `components/icons.tsx`,
  en el mismo estilo de línea de los cuatro existentes: `stroke: currentColor`,
  `stroke-width: 1.6`, 24×24, sin `fill`).
- La cabecera de cada pantalla de gestión se estandariza: `<div class="page-header">` con
  `h2` a la izquierda, descripción `--text-muted` debajo y el botón primario a la derecha.
  Hoy cada pantalla lo resuelve distinto (`.panel-filters` mezcla título, filtros y botón).

### 7.3 Catálogo (`CatalogView`, `BookResults`, `BookCover`, `SearchBar`)

Es la pantalla que más gana con el rediseño y la que primero se ve.

- **Buscador**: se agranda a altura 52px, `--radius-full`, `--shadow-sm`, y en foco toma
  `--ring`. Se mantiene el botón "Limpiar" como `.btn-ghost .btn-sm`. Ancho máximo 640px
  centrado, con un texto de apoyo debajo (`--text-muted`, `--text-sm`) del estilo "Buscá entre
  N libros de la red" usando el `total` que ya devuelve `GET /books`.
- **Grilla**: `repeat(auto-fill, minmax(160px, 1fr))` (hoy 146px) y `gap: var(--space-6) var(--space-4)`
  — más aire vertical que horizontal, porque debajo de cada portada hay dos líneas de texto.
- **Tarjeta de libro**: la portada toma `--radius-md`, `--shadow-sm` y un borde de 1px. En
  hover: `transform: translateY(-3px)` y `--shadow-md` (ya existe, se afina). Se agrega un
  overlay sutil al hover con el texto "Ver disponibilidad" en la base de la portada, que en
  `prefers-reduced-motion` aparece sin transición.
- **Seleccionado**: hoy es `outline: 2px solid` + título en acento. Con el modal abierto eso
  ya casi no se ve; se reduce a un `box-shadow: var(--ring)` sobre la portada.
- **Placeholder sin portada**: se mantiene el reemplazo tipográfico (es un acierto), pero con
  un degradado por libro en vez de uno solo para todos: color derivado del ISBN
  (`hue = hash(isbn) % 360` calculado en `BookCover.tsx` y pasado como
  `style={{ "--cover-hue": … }}`), con saturación y luminosidad fijas por token para que
  ninguno quede estridente ni ilegible. Es lo que hace que una grilla sin portadas —el estado
  real hoy, el seed no carga imágenes— se vea intencional.
- **Cabecera de resultados**: el "Catálogo · 12 de 71" pasa a `h2` + `.badge-neutral`.
- **Carga**: skeletons en vez de "Cargando catálogo…" (6.10).
- **"Cargar más"**: `.btn-secondary` centrado, con el remanente en el texto ("Cargar más — 59
  restantes").

### 7.4 Ficha del libro (modal: `BookAvailabilityView`)

- Cabecera a dos columnas: portada 140px a la izquierda (hoy 110px), a la derecha eyebrow +
  título en `--text-xl` con `--font-display` + autores en `--text-muted`, y los géneros como
  `.badge-neutral` en fila. Los géneros hoy no se muestran en la ficha: hay que agregarlos,
  `BookOut` ya los trae.
- La sinopsis va a `--leading-normal` y `max-width: 62ch`.
- ISBN, idioma y páginas pasan a una fila de metadatos `--text-xs` separados por `·` al pie
  de la cabecera.
- La lista de sedes (`.library-list`) se rediseña como filas sin caja: separador
  `border-bottom: 1px solid var(--border)` en vez de tarjeta con borde completo, nombre en
  `--text-base` peso 550, ciudad en `--text-muted`, el contador de copias como
  `.badge-success` cuando hay stock, y el botón "Reservar" `.btn-primary .btn-sm` a la
  derecha.
- Estado vacío ("no hay ejemplares disponibles"): `.callout .callout-neutral`, no un `.empty`
  en itálica.

### 7.5 Panel bibliotecario y Mis reservas

- Ambas pantallas adoptan `.page-header` + `.card-flush` con la tabla adentro.
- Los filtros (`.segmented-sm`) y el selector de sede se agrupan en una barra propia con
  `border-bottom: 1px solid var(--border)` arriba de la tabla, en vez de flotar sueltos.
- Columna Estado: `.badge-*` renombrados (6.5).
- **Vencimiento**: cuando `expires_at` ya pasó y la reserva sigue abierta, la fecha se muestra
  en `--danger` con el badge correspondiente. Hoy una reserva en mora se ve igual que una al
  día, y el seed genera varias a propósito.
- Botón "Gestionar" `.btn-secondary .btn-sm`; en el modal, las acciones se ordenan
  primaria-primero y la destructiva separada por un `margin-left: auto`.

### 7.6 Perfil y auth

- `.profile-view` a `--container-narrow`, `gap: var(--space-6)`.
- Tres tarjetas: **Perfil** (datos), **Apariencia** (el selector de tema, 4.2) y **Zona de
  peligro** (`.card-danger`). Hoy son dos y el logout está mezclado con "Guardar cambios":
  el logout pasa a `.btn-ghost` alineado a la izquierda, separado del submit por
  `margin-right: auto`.
- La nota de alcance (sede a cargo) pasa a `.callout .callout-accent` con el ícono de sede.
- `.auth-view`: la tarjeta se centra verticalmente (`min-height: calc(100vh - var(--header-height))`),
  con el wordmark arriba y el link cruzado (Ingresar ↔ Crear cuenta) al pie, en `--text-sm`.

### 7.7 Sedes

`.library-cards` pasa a `minmax(19rem, 1fr)` con `.card`; el nombre en `--font-display`
`--text-md`, la dirección con el `PinIcon` en `--text-muted`, y `.library-meta` como lista de
definición a dos columnas con `--text-sm`. Agregar `word-break` en el sitio web (ya está como
`overflow-wrap: anywhere`, se mantiene).

---

## 8. Accesibilidad (requisitos, no sugerencias)

1. **Foco visible en todo lo interactivo.** Una regla base
   `:where(a, button, input, select, textarea, [tabindex]):focus-visible { outline: none; box-shadow: var(--ring) }`
   y prohibido volver a escribir `outline: none` suelto.
2. **Contraste AA**: ≥4.5:1 texto normal, ≥3:1 texto grande y bordes de controles. Verificar
   en los dos temas, con foco en: `--text-muted` sobre `--bg-subtle`, cada `--*-soft` con su
   color de estado (los badges), y `--text-on-accent` sobre `--accent`. Si alguno no da, se
   ajusta el token, no se parchea la regla.
3. **Áreas táctiles ≥40px** de alto en controles de formulario y ≥32px en botones de fila
   (con `padding` que llegue a esa altura, no solo `min-height`).
4. `prefers-reduced-motion: reduce` desactiva todas las animaciones y transiciones con un
   bloque único al final de la capa 2. Las tres animaciones existentes (toast-in, hover de
   portada, entrada del modal) tienen que estar contempladas ahí.
5. El `.segmented` de navegación mantiene los `<NavLink>`: es navegación, no `role="tablist"`.
   El de tema en el perfil sí lleva `role="radiogroup"` + `aria-checked`.
6. `.visually-hidden` como utilidad para etiquetas de íconos sin texto.

---

## 9. Plan de migración

Siete pasos. Cada uno deja la app funcionando y verificable con `npm run build` + una pasada
visual; no hay un paso "todo roto en el medio".

| # | Paso | Qué toca | Hecho cuando |
|---|---|---|---|
| 1 | Capa de tokens | `index.css` (solo el `:root`) + reemplazo de nombres viejos | La app se ve *casi* igual pero con la paleta nueva; cero `#hex` fuera de la capa 1 |
| 2 | Base y foco | Capa 2 completa | Recorrer la app entera con Tab: todo control muestra el anillo |
| 3 | Primitivas | Capa 3 + `className` en los `.tsx` | Ningún botón/input/tarjeta se estiliza fuera de la capa 3; se borran las ~40 reglas duplicadas |
| 4 | Modo oscuro | `lib/theme.ts`, `ThemeContext`, `main.tsx`, `index.html`, `ProfileView` | Se cambia de tema sin recargar, sobrevive al refresh, sin flash, y ninguna pantalla tiene texto ilegible |
| 5 | Catálogo | Capa 4 (catálogo + ficha), `BookCover.tsx` | Grilla, hover, skeletons y placeholder por color implementados |
| 6 | Navegación | `App.tsx`, `admin/AdminLayout.tsx`, íconos nuevos | Header sticky y sidebar de gestión en ≥900px; en mobile no hay scroll horizontal de página |
| 7 | Tablas, gestión, perfil, auth, sedes | Resto de la capa 4 | Checklist de la sección 11 en verde |

Antes del paso 1, borrar `.librarian-name` (l. 1018-1040): está muerta.

**Riesgos conocidos**

- El paso 3 es el que más `.tsx` toca (16 archivos) aunque solo cambie `className`. Conviene
  hacerlo pantalla por pantalla y no en un solo commit.
- `color-mix()` y `backdrop-filter` no están en navegadores viejos: ambos usos tienen que
  tener fallback plano declarado antes (un color sólido del sistema de tokens).
- El header sticky con `backdrop-filter` sobre la grilla de portadas puede costar en mobile;
  si se nota, se cambia por fondo opaco `--bg`.
- No hay tests visuales ni linter de CSS: la única verificación automática sigue siendo
  `npm run build`. Todo lo visual se revisa a ojo, en los dos temas.

---

## 10. Reglas de la casa para el CSS nuevo

Para que el sistema no se degrade como el actual:

1. **Ningún color literal fuera de la capa 1.** Ni `#hex`, ni `rgb()`, ni `rgba()`.
2. **Ningún `rem` suelto en `padding`, `margin` o `gap`**: siempre `var(--space-*)`. Los
   tamaños de fuente, siempre `var(--text-*)`.
3. **Una primitiva no se redefine desde una pantalla.** Si `.btn` no alcanza, se agrega una
   variante en la capa 3.
4. **Nada de `!important`** y máximo dos niveles de anidado de selectores.
5. **Ninguna regla nueva con `[data-theme="dark"]`** fuera de la capa 1 (ver 4.3).
6. Clases nombradas por **qué es**, no por dónde está ni cómo se ve: `.card`, no
   `.librarian-panel`; `.badge-danger`, no `.status-cancelled`.
7. Al agregar un componente: primero buscar si alguna primitiva ya lo resuelve; recién
   después escribir CSS.

---

## 11. Checklist de cierre

Recorrer con las dos paletas (claro y oscuro) y en dos anchos (375px y 1440px):

- [ ] Catálogo: grilla con y sin portadas, hover, seleccionado, "Cargar más", buscador con
      resultados y sin resultados, skeleton de carga.
- [ ] Ficha del libro: con stock y sin stock, sinopsis larga y sin sinopsis, formulario de
      reserva abierto, error 409 (toast) sobre el modal.
- [ ] Mis reservas y Panel: los cinco estados de reserva, una reserva en mora, tabla vacía,
      tabla de 190 filas con encabezado sticky, modal de gestión en sus tres variantes
      (sin retirar / retirada / cerrada).
- [ ] Gestión: sidebar en desktop y segmented en mobile; tabla de ejemplares (6 columnas) en
      375px; formulario de libro con portada cargada, sin portada y con error 422.
- [ ] Perfil: las tres tarjetas, el selector de tema en sus tres estados, la nota de sede
      para librarian / sysadmin / customer.
- [ ] Auth: login con error de credenciales, registro con 422.
- [ ] Toasts: las cuatro variantes, cuatro apilados, uno sobre un modal abierto.
- [ ] Teclado: recorrer cada pantalla con Tab sin perder el foco de vista; Escape cierra el
      modal; el foco vuelve al disparador al cerrarlo.
- [ ] `prefers-reduced-motion: reduce` activo: nada se mueve.
- [ ] `npm run build` limpio.

---

## 12. Inventario de clases: destino de cada una

| Clase actual | Destino |
|---|---|
| `.app`, `.app-header`, `.brand`, `.tagline` | Se quedan; nuevos valores (7.1) |
| `.logo-*`, `.brand-mark` | Sin cambios (el logo no se rediseña) |
| `.tabs`, `.subtabs`, `.filters` | → `.segmented` (+ `.segmented-sm`) |
| `.session`, `.session-link` | `.session` se queda; el link → `.btn` |
| `.search-bar*` | Se quedan; el botón → `.btn` |
| `.catalog-layout`, `.catalog-results*` | Se quedan; nuevos valores |
| `.book-grid`, `.book-cover*` | Se quedan; nuevos valores (7.3) |
| `.availability*`, `.library-list` | Se quedan; rediseño de 7.4 |
| `.catalog-detail`, `.form-card`, `.reservation-form`, `.librarian-panel` | → `.card` (+ variantes) |
| `.confirm-button`, `.row-button`, `.danger-button`, `.load-more`, `.modal-close`, `.toast-close`, `.chip-remove` | → `.btn` + variantes |
| `.inline-select`, `.inline-input`, `.field-hint` | → `.field` + variantes |
| `.badge`, `.role-chip`, `.status-badge`, `.status-*` | → `.badge` + variantes de color |
| `.error`, `.success`, `.api-status`, `.scope-note` | → `.callout` + variantes |
| `.table-wrap`, `th`, `td` | Se quedan; rediseño de 6.7 |
| `.modal*`, `.toast*` | Se quedan; rediseño de 6.8 y 6.9 |
| `.chip-select`, `.chips`, `.chip`, `.chips-empty` | Se quedan; tokens nuevos |
| `.detail-grid`, `.manage-actions`, `.extend-form` | Se quedan |
| `.library-cards`, `.library-address`, `.library-meta` | Se quedan; rediseño de 7.7 |
| `.empty-state`, `.empty`, `.muted`, `.hint`, `.eyebrow` | Se quedan como utilidades (capa 5) |
| `.panel-filters` | → `.page-header` (7.2) |
| `.librarian-name` | **Borrar**: sin uso |
| `.row-actions`, `.actions` | Se quedan |
| — | **Nuevas**: `.btn*`, `.field*`, `.card*`, `.segmented*`, `.callout*`, `.skeleton`, `.page-header`, `.visually-hidden`, `.theme-toggle` |
