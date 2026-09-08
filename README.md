# BookUp

Plataforma nacional de catálogo y búsqueda bibliotecaria: centraliza la búsqueda,
disponibilidad y reserva de libros entre todas las sedes de la red, con acceso
tanto desde las bibliotecas como desde los hogares de los usuarios.

Este repo contiene el MVP: un backend monolítico en capas (API + base de
datos) y un frontend en React, pensados para correr localmente con Docker y
luego desplegarse sobre servicios gestionados de AWS.

## Stack

- **API**: Python 3.12 + FastAPI, monolito en capas (persistence / services /
  controllers)
- **Base de datos**: PostgreSQL 16, migraciones con Alembic
- **Frontend**: React 18 + TypeScript + Vite
- **Local dev**: Docker Compose

## Estructura

```
api/
  app/
    main.py               # app FastAPI, CORS, registro de excepciones/rutas
    config.py               # settings (DATABASE_URL, CORS, etc.)
    persistence/              # capa de datos: no sabe nada de HTTP
      database.py               # engine, sesión, Base
      models.py                  # entidades ORM: User, Library, Book, Author,
                                 #   Genre, PhysicalBook, Reservation
      repositories/                # acceso a datos por entidad
    services/                  # lógica de negocio, no depende de FastAPI
      catalog_service.py           # búsqueda y disponibilidad cruzada
      library_service.py
      reservation_service.py
      user_service.py
      errors.py                     # NotFoundError / ConflictError (dominio)
    controllers/               # capa HTTP: routers + esquemas Pydantic
      catalog_controller.py
      library_controller.py
      reservation_controller.py
      user_controller.py
      schemas.py
    seed.py                    # carga de datos de ejemplo
  alembic/                   # migraciones de base de datos
  tests/                      # tests con pytest
frontend/
  src/
    api.ts                     # cliente HTTP hacia la API
    types.ts                    # tipos que reflejan los esquemas del backend
    components/                  # SearchBar, BookResults, ReservationForm, ...
    App.tsx
docker-compose.yml
```

Las dependencias siempre apuntan hacia adentro: `controllers` conoce a
`services`, `services` conoce a `persistence`, pero `persistence` no conoce a
`services` ni a FastAPI, y `services` no conoce HTTP (las excepciones de
dominio como `NotFoundError`/`ConflictError` se mapean a códigos HTTP recién
en `main.py`).

## Cómo correrlo local

Requiere Docker y Docker Compose.

```bash
docker compose up --build
```

Esto levanta Postgres, corre las migraciones de Alembic, expone la API en
`http://localhost:8000` (docs interactivas en `http://localhost:8000/docs`)
y el frontend en `http://localhost:5173`.

Para cargar datos de ejemplo (bibliotecas, libros, ejemplares y usuarios):

```bash
docker compose exec api python -m app.seed
```

El seed crea tres sedes (Central, Norte y Sur) con su personal. **Todos los
usuarios comparten la password `bookup123`:**

| Email | Password | Rol | Sede a cargo |
|---|---|---|---|
| `admin@bookup.example` | `bookup123` | sysadmin | — (ve y administra todas) |
| `central@bookup.example` | `bookup123` | librarian | Biblioteca Central |
| `norte@bookup.example` | `bookup123` | librarian | Biblioteca del Norte |
| **`sur@bookup.example`** | **`bookup123`** | **librarian** | **Biblioteca Sur** |
| `ana@bookup.example` | `bookup123` | customer | — |

Para administrar la **Biblioteca Sur**, entrá en `http://localhost:5173` con
`sur@bookup.example` / `bookup123`. Con ese usuario vas a ver:

- **Panel bibliotecario**: las reservas de la sede Sur, con retiro, devolución,
  cancelación y extensión del vencimiento.
- **Gestión → Ejemplares**: alta y baja de ejemplares de esa sede (la sede queda
  fijada, un librarian no puede tocar otra).
- **Gestión → Sedes**: el formulario de edición de la Biblioteca Sur únicamente;
  el alta y la baja de sedes son de `sysadmin`.
- **Gestión → Libros / Autores / Géneros**: el catálogo es compartido por toda la
  red, así que se edita completo desde cualquier sede.

Las pantallas de **Usuarios** y **Mantenimiento** no le aparecen: son de
`sysadmin` (entrá con `admin@bookup.example` para eso). Sin al menos un sysadmin
no se pueden crear sedes ni personal por la API, por eso el seed lo bootstrapea.

### Backend sin Docker

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # ajustar DATABASE_URL si hace falta
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd api && pytest
```

### Frontend sin Docker

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_URL, por defecto http://localhost:8000
npm run dev
```

## Endpoints del MVP

La superficie completa está documentada en [`api/openapi.yml`](api/openapi.yml).

Salvo el catálogo, las sedes (lectura) y el auto-registro, todo pide un JWT en
`Authorization: Bearer <token>`. La columna "Acceso" indica qué rol lo puede usar.

| Método | Ruta                              | Descripción                                    | Acceso |
|--------|------------------------------------|-------------------------------------------------|--------|
| POST   | `/auth/login`                      | Obtener un token                                | público |
| GET    | `/auth/me`                         | Usuario autenticado                             | autenticado |
| GET    | `/health`                          | Health check                                    | público |
| GET    | `/books`                           | Listado del catálogo                            | público |
| POST   | `/books`                           | Alta de un libro (ISBN-13 validado)             | librarian o sysadmin |
| GET    | `/books/search?q=`                 | Búsqueda unificada por título/autor/ISBN/sinopsis | público |
| GET    | `/books/{isbn}`                    | Detalle de un libro                             | público |
| PATCH  | `/books/{isbn}`                    | Actualización parcial de un libro               | librarian o sysadmin |
| DELETE | `/books/{isbn}`                    | Baja de un libro (409 si tiene ejemplares)      | librarian o sysadmin |
| GET    | `/books/{isbn}/availability`       | Disponibilidad por biblioteca (stock cruzado)   | público |
| GET    | `/authors`, `/authors/{id}`        | Autores del catálogo                            | público |
| POST/PATCH/DELETE | `/authors[/{id}]`       | ABM de autores (409 al borrar si tiene libros)  | librarian o sysadmin |
| GET    | `/genres`, `/genres/{id}`          | Géneros del catálogo                            | público |
| POST/PATCH/DELETE | `/genres[/{id}]`        | ABM de géneros (nombre único)                   | librarian o sysadmin |
| GET    | `/physical-books?isbn=&library_id=&status=` | Ejemplares físicos, filtrables         | público |
| GET    | `/physical-books/{id}`             | Detalle de un ejemplar                          | público |
| POST   | `/physical-books`                  | Alta de un ejemplar en una sede                 | sysadmin, o el librarian de esa sede |
| PATCH  | `/physical-books/{id}/status`      | Marcar `lost` / volver a `available`            | sysadmin, o el librarian de esa sede |
| DELETE | `/physical-books/{id}`             | Baja de un ejemplar (409 si tiene reservas)     | sysadmin, o el librarian de esa sede |
| GET    | `/libraries`                       | Listado de bibliotecas/sedes                    | público |
| POST   | `/libraries`                       | Alta de biblioteca                              | sysadmin |
| GET    | `/libraries/{id}`                  | Detalle de una sede                             | público |
| PATCH  | `/libraries/{id}`                  | Actualización parcial de una sede               | sysadmin, o el librarian de esa sede |
| DELETE | `/libraries/{id}`                  | Baja de una sede (409 si tiene ejemplares)      | sysadmin |
| POST   | `/reservations`                    | Reservar un ejemplar disponible (a nombre del usuario del token) | autenticado |
| GET    | `/reservations?library_id=&is_open=` | Listado de reservas                           | sysadmin (todas), librarian (su sede), customer (las propias) |
| GET    | `/reservations/{id}`               | Detalle de una reserva                          | dueño, librarian de la sede, o sysadmin |
| PATCH  | `/reservations/{id}`               | Extender el vencimiento                         | librarian de la sede, o sysadmin |
| PATCH  | `/reservations/{id}/pickup`        | Marcar la reserva como retirada en la sede      | librarian de la sede, o sysadmin |
| PATCH  | `/reservations/{id}/return`        | Registrar la devolución del ejemplar            | librarian de la sede, o sysadmin |
| POST   | `/reservations/{id}/cancel`        | Cancelar una reserva no retirada                | dueño, librarian de la sede, o sysadmin |
| POST   | `/reservations/expire`             | Vencer las reservas no retiradas (idempotente)  | sysadmin |
| POST   | `/users`                           | Auto-registro (rol `customer` fijo)             | público |
| POST   | `/users/staff`                     | Alta de librarian/sysadmin                      | sysadmin |
| GET    | `/users`                           | Listado de usuarios                             | sysadmin |
| GET    | `/users/{id}`                      | Detalle de un usuario                           | el propio usuario, o sysadmin |
| PATCH  | `/users/{id}`                      | Actualización parcial (`role`/`library_id` solo sysadmin) | el propio usuario, o sysadmin |
| DELETE | `/users/{id}`                      | Baja de un usuario                              | el propio usuario, o sysadmin |

## Frontend

SPA con React Router y sesión propia (JWT en `localStorage`). Cada pantalla se
muestra según el rol del token; detalle y decisiones en
[`frontend/ROADMAP.md`](frontend/ROADMAP.md).

| Pantalla | Acceso |
|---|---|
| Catálogo: buscar, ver disponibilidad por sede y reservar | público (reservar pide sesión) |
| Sedes: listado con dirección, horarios y contacto | público |
| Ingresar / Crear cuenta | público |
| Mis reservas: seguimiento y cancelación | autenticado |
| Mi perfil: datos, contraseña y baja de cuenta | autenticado |
| Panel bibliotecario: retiro, devolución, cancelación y extensión | librarian (su sede) / sysadmin |
| Gestión → Libros, Autores, Géneros | librarian / sysadmin |
| Gestión → Ejemplares | librarian (su sede) / sysadmin |
| Gestión → Sedes | librarian (edita la suya) / sysadmin (ABM completo) |
| Gestión → Usuarios, Mantenimiento | sysadmin |

## De este MVP a la arquitectura en AWS

Este backend está pensado para mapear directo a los servicios gestionados
descriptos en la propuesta:

- **Cómputo**: la API FastAPI corre en contenedores (ECS Fargate) o Lambda
  detrás de API Gateway, con auto-scaling y despliegue multi-AZ. El frontend
  se sirve como estático desde S3 + CloudFront.
- **Base de datos**: RDS PostgreSQL Multi-AZ (réplicas de lectura por región
  para consultar stock del resto de la red sin afectar el nodo de escritura).
- **Búsqueda**: el `ILIKE` de `/books/search` (en `BookRepository`) es un
  placeholder; en producción el índice lo sirve OpenSearch, alimentado desde
  Postgres.
- **Analítica**: un proceso ETL (Glue) copia datos hacia un data warehouse
  (Redshift/Athena sobre S3), separado de la base operativa.
- **API pública**: API Gateway con autenticación, rate limiting y métricas
  para exponer el catálogo a bibliotecas externas.
- **Portal de bibliotecarios**: la API ya emite y valida sus propios JWT
  (`POST /auth/login`, HS256 con `JWT_SECRET`) y aplica roles
  `customer`/`librarian`/`sysadmin`. En la arquitectura target ese emisor lo
  reemplaza Cognito: el resto de la autorización por rol ya está en su lugar.
- **Redes**: VPC con subnets públicas (ALB/API Gateway, CloudFront) y privadas
  (RDS, tareas de cómputo).

## Próximos pasos

- Migrar la emisión de tokens propia a Cognito.
- Integrar OpenSearch para la búsqueda de catálogo.
- Definir el pipeline ETL hacia el data warehouse.
- Infraestructura como código (Terraform/CDK) para el despliegue en AWS.
