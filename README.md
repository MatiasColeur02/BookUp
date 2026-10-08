# BookUp

Plataforma nacional de catálogo y búsqueda bibliotecaria: centraliza la búsqueda,
disponibilidad y reserva de libros entre todas las sedes de la red, con acceso
tanto desde las bibliotecas como desde los hogares de los usuarios.

Este repo contiene el MVP: un backend monolítico en capas (API + DynamoDB +
índice de búsqueda) y un frontend en React, pensados para correr localmente con
Docker y luego desplegarse sobre servicios gestionados de AWS.

## Stack

- **API**: Python 3.12 + FastAPI, monolito en capas (persistence / services /
  controllers)
- **Base de datos**: DynamoDB, tabla única (DynamoDB Local en desarrollo). Sin migraciones: la
  forma de la tabla la define `app/persistence/table.py`
- **Búsqueda del catálogo**: OpenSearch, alimentado desde el stream de la tabla por un indexador
- **Cache**: Redis 7 (ElastiCache for Redis en AWS)
- **Portadas**: almacenamiento de objetos S3-compatible (MinIO en local, S3 en AWS)
- **Frontend**: React 18 + TypeScript + Vite
- **Local dev**: Docker Compose

## Estructura

```
api/
  app/
    main.py               # app FastAPI, CORS, registro de excepciones/rutas
    config.py               # settings (DYNAMO_TABLE, OPENSEARCH_URL, REDIS_URL, CORS, etc.)
    cache.py                 # cache de lecturas sobre Redis
    storage.py                # portadas de libros sobre S3 (URLs firmadas)
    indexer.py                # stream de DynamoDB -> índice de búsqueda (Lambda / poller local)
    reindex.py                # reconstruye el índice de búsqueda entero
    persistence/              # capa de datos: no sabe nada de HTTP
      dynamo.py                 # cliente y recurso de la tabla (`Dynamo`)
      keys.py                    # formato de las claves: el único lugar que lo conoce
      entities.py                 # entidades (dataclasses): User, Library, Book, Author,
                                  #   Genre, PhysicalBook, Reservation
      table.py                     # creación de la tabla y sus 4 GSIs
      search.py                     # índice de búsqueda del catálogo (OpenSearch)
      errors.py                      # ConditionFailedError / SearchUnavailableError
      repositories/                 # acceso a datos por entidad
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
  tests/                      # tests con pytest (contra DynamoDB Local y OpenSearch)
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
en `main.py`). Los services tampoco ven boto3, claves ni transacciones: reciben
un `Dynamo` y hablan con repositories, así que cambiar de motor de datos tocaría
solo `persistence/`.

## Cómo correrlo local

Requiere Docker y Docker Compose.

```bash
docker compose up --build
```

Esto levanta DynamoDB Local (con la tabla ya creada), OpenSearch, Redis y MinIO (con el
bucket de portadas ya creado), expone la API en `http://localhost:8000` (docs interactivas
en `http://localhost:8000/docs`) y el frontend en `http://localhost:5173`. La consola de
MinIO queda en `http://localhost:9001` (`bookup` / `bookup123`).

| Servicio | Para qué | Puerto |
|---|---|---|
| `dynamodb` | DynamoDB Local, con volumen: tus datos de desarrollo | 8001 |
| `dynamodb-init` | One-shot: crea la tabla `bookup` y sus 4 GSIs (idempotente) | — |
| `dynamodb-test` | DynamoDB Local **en memoria**, solo para `pytest` | 8002 |
| `search` | OpenSearch (un nodo, sin seguridad: es desarrollo) | 9200 |
| `indexer` | Lee el stream de la tabla y mantiene el índice de búsqueda; al arrancar lo crea y lo llena | — |
| `cache` / `storage` / `storage-init` | Redis y MinIO (más la creación del bucket) | 6379 / 9000, 9001 |
| `api` / `web` | La API y el frontend | 8000 / 5173 |

OpenSearch usa ~1 GB de RAM. Si el disco de la VM de Docker se llena, `docker system prune`
(o borrar caché de build) suele ser suficiente.

Para cargar datos de ejemplo (bibliotecas, libros, ejemplares y usuarios):

```bash
docker compose exec api python -m app.seed
```

El seed carga un dataset completo y **determinista** (mismo resultado en cualquier
máquina): 10 sedes de todo el país, 71 libros de 53 autores en 16 géneros, ~400
ejemplares repartidos entre las sedes y ~190 reservas que cubren todo el ciclo de vida
(abiertas sin retirar, prestadas, algunas en mora, devueltas, canceladas y vencidas).
Volver a correrlo no duplica nada: si ya hay datos, no hace nada. Deja los contadores de
ids en el último valor usado (el primer alta por la API no pisa nada sembrado) y reindexa el
catálogo. Si la tabla ya tiene datos creados por la API pero nunca se sembró, se niega a
mezclarse con ellos en vez de pisarlos.

Para **empezar de cero** (tabla vacía y sembrada de nuevo), borrá la tabla y volvé a
crearla y sembrarla; el indexador detecta solo que la tabla se recreó y reindexa:

```bash
docker compose exec api python -c "from app.persistence.dynamo import get_dynamo; from app.persistence.table import drop_table; drop_table(get_dynamo())"
docker compose exec api sh -c "python -m app.persistence.table && python -m app.seed"
```

Hay un bibliotecario por sede (`<sede>@bookup.example`), dos sysadmins y 20 lectores.
**Todos los usuarios comparten la password `bookup123`:**

| Email | Password | Rol | Sede a cargo |
|---|---|---|---|
| `admin@bookup.example` | `bookup123` | sysadmin | — (ve y administra todas) |
| `central@bookup.example` | `bookup123` | librarian | Biblioteca Central |
| `norte@bookup.example` | `bookup123` | librarian | Biblioteca del Norte |
| **`sur@bookup.example`** | **`bookup123`** | **librarian** | **Biblioteca Sur** |
| `ana@bookup.example` | `bookup123` | customer | — (tiene reservas en todos los estados) |

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

La API necesita los servicios de arriba. Los más prácticos son los del compose, y la API
corre en tu máquina contra ellos:

```bash
docker compose up -d dynamodb dynamodb-init search cache storage storage-init
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # los endpoints de .env.example apuntan a localhost
python -m app.seed        # crea el índice y reindexa el catálogo
uvicorn app.main:app --reload
python -m app.indexer     # en otra terminal: mantiene el índice al día
```

Tests. Necesitan DynamoDB Local en memoria y OpenSearch, y fallan —no se saltean— si no
los encuentran. La suite usa su propio `dynamodb-test` y nunca toca tu tabla `bookup`:

```bash
docker compose up -d dynamodb-test search
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

**Consistencia.** Todo lo que se lee por clave —el detalle de un libro, la disponibilidad, las
respuestas de los `POST`/`PATCH`, reservas, usuarios— es consistente: se ve lo que se acaba de
escribir. Solo el listado del catálogo (`GET /books`, `/books/search`, `/books/cities`) sale del
índice de búsqueda y es **eventualmente consistente**: un libro recién creado tarda ~1 s en
aparecer en él. Si el índice no está disponible esos tres endpoints dan 503 y el resto sigue.

Salvo el catálogo, las sedes (lectura) y el auto-registro, todo pide un JWT en
`Authorization: Bearer <token>`. La columna "Acceso" indica qué rol lo puede usar.

| Método | Ruta                              | Descripción                                    | Acceso |
|--------|------------------------------------|-------------------------------------------------|--------|
| POST   | `/auth/login`                      | Obtener un token                                | público |
| GET    | `/auth/me`                         | Usuario autenticado                             | autenticado |
| GET    | `/health`                          | Health check                                    | público |
| GET    | `/books?q=&author_id=&genre_id=&city=&limit=&offset=` | Catálogo paginado, con búsqueda y filtros combinables (índice de búsqueda: ~1 s de retraso, 503 si no está) | público |
| GET    | `/books/cities`                    | Ciudades con stock disponible (opciones del filtro) | público |
| POST   | `/books`                           | Alta de un libro (ISBN-13 validado)             | librarian o sysadmin |
| GET    | `/books/search?q=`                 | Búsqueda unificada por título/autor/ISBN/sinopsis (índice de búsqueda) | público |
| GET    | `/books/{isbn}`                    | Detalle de un libro (de la base: consistente)   | público |
| PATCH  | `/books/{isbn}`                    | Actualización parcial de un libro               | librarian o sysadmin |
| DELETE | `/books/{isbn}`                    | Baja de un libro (409 si tiene ejemplares)      | librarian o sysadmin |
| POST   | `/books/{isbn}/cover-upload`       | URL firmada para subir la portada a S3          | librarian o sysadmin |
| PUT    | `/books/{isbn}/cover`              | Confirmar la portada subida                     | librarian o sysadmin |
| DELETE | `/books/{isbn}/cover`              | Quitar la portada (borra el objeto del bucket)  | librarian o sysadmin |
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

## Cache

Las lecturas públicas se sirven desde Redis (`api/app/cache.py`). El cache vive en la
capa de `controllers`: lo que se guarda son payloads JSON ya serializados por los
esquemas Pydantic, no entidades ORM, así que `services` y `persistence` siguen sin
enterarse de que existe — igual que no se enteran de HTTP.

| Endpoint | TTL | Por qué |
|---|---|---|
| `GET /books/search?q=` | 120 s | La lectura más cara del catálogo: texto libre sobre el índice de búsqueda |
| `GET /books` (sin `city`), `GET /books/{isbn}` | 300 s | El catálogo es de lectura casi pura |
| `GET /books?city=`, `GET /books/cities` | 30 s | Dependen del stock disponible: cambian con cada reserva, así que van al namespace de disponibilidad |
| `GET /books/{isbn}/availability` | 30 s | La pantalla más visitada, pero también la que más rápido queda vieja |
| `GET /libraries`, `/authors`, `/genres` (+ detalle) | 600 s | Datos de referencia que casi nunca cambian |

No se cachean `/reservations`, `/users` ni `/auth/me`: la respuesta depende del usuario
del token, así que una entrada compartida filtraría datos de una persona a otra.
Tampoco `/physical-books`, que es la pantalla de gestión de un bibliotecario (poco
tráfico, mucha volatilidad, y tres filtros que multiplicarían las entradas).

**Invalidación por generaciones.** Cada namespace tiene un contador cuyo valor va dentro
de la clave; invalidar es un `INCR` O(1) y las claves viejas quedan huérfanas hasta que
vence su TTL. Evita barrer con `KEYS`/`SCAN`, que en ElastiCache bloquea el nodo. Las
escrituras invalidan siguiendo cómo se embeben los esquemas: renombrar un autor refresca
el catálogo y la disponibilidad, reservar o devolver un ejemplar refresca la
disponibilidad. El listado del catálogo sale de un índice que se actualiza ~1 s después de
cada escritura, así que **el indexador también invalida** el catálogo, y lo hace después de
forzar el refresco del índice: invalidar antes dejaría que una lectura en esa ventana
recachee la lista vieja por 5 minutos.

**El cache nunca tira abajo la API.** Todo error de Redis se traga y se sirve desde la
base, y un breaker lo apaga 10 s para que un nodo caído no le sume timeouts a cada
request. Sin `REDIS_URL` queda directamente apagado — así corren los tests, y así se
puede levantar la API sin Redis. `GET /health` reporta `cache: ok | down | disabled`.

## Validación de entrada y rate limiting

Toda entrada del cliente tiene un techo, y el techo está en el backend: el frontend
repite los mismos números (`frontend/src/lib/limits.ts`) solo para no hacer escribir 400
caracteres y devolver un 422 recién al enviar.

| Riesgo | Qué lo corta |
|---|---|
| Inyección | No hay SQL: los datos van a DynamoDB como valores tipados. El texto libre del catálogo va a OpenSearch como `multi_match` y **nunca como `query_string`**, que interpreta operadores del usuario (`*`, `OR`, `~`, `campo:`) y deja armar consultas carísimas a propósito |
| Texto larguísimo (nombres, sinopsis) | `max_length` en los esquemas Pydantic. Sin él, un nombre de 5.000 caracteres llega a la capa de datos (un ítem de DynamoDB admite 400 KB) y sale como **500**; con él es un 422 |
| Portada enorme | Doble barrera: el tamaño declarado al pedir la URL firmada, y el tamaño **real** del objeto (un `HEAD`) al confirmarla. Lo que no cumple se borra del bucket y nunca llega a la fila |
| Cuerpo de request gigante | Middleware de 1 MB por `Content-Length`, antes de leer el cuerpo (413) |
| Fuerza bruta sobre el login | Rate limit por IP y por cuenta sobre Redis (429 + `Retry-After`) |
| Alta masiva de cuentas | Rate limit por IP en `POST /users` |
| Reserva que retiene un ejemplar para siempre | `expires_at` tiene techo (365 días), no solo piso |
| Contraseña que bcrypt truncaría | Se rechaza lo que pase de 72 bytes en vez de truncarlo en silencio |

Dos decisiones del rate limiting que no son obvias:

- **Es fail-open.** Si Redis se cae, se deja pasar el request. Un límite anti-abuso no
  puede dejar a todo el mundo afuera del login por un problema de infraestructura; el
  control que **no** puede fallar así es la autorización por rol, y ese no depende de
  Redis. Sin `REDIS_URL` el límite queda apagado, igual que el cache.
- **El contador por cuenta cuenta solo intentos fallidos, y se evalúa después de
  autenticar.** Si se evaluara antes, cualquiera podría dejar a otra persona afuera de su
  cuenta tirándole diez contraseñas incorrectas. Así, lo único que se bloquea es seguir
  adivinando: la contraseña correcta siempre entra.

En la arquitectura target esto no reemplaza al rate limiting de API Gateway/WAF, que
corta antes de llegar al cómputo; lo complementa con el límite por cuenta, que el borde
no puede aplicar porque no sabe qué email se está intentando.

## Portadas de libros

Las portadas viven en un bucket S3 (MinIO en local, `S3_BUCKET` en AWS). **La imagen
nunca pasa por la API**: el cliente pide una URL firmada, hace el `PUT` directo al
bucket y recién después confirma la key.

```
browser → API   POST /books/{isbn}/cover-upload  { content_type, size }
API    → browser  { upload_url, key, ... }        ← URL firmada, 15 min
browser → S3     PUT <upload_url>                 ← el archivo, sin pasar por la API
browser → API    PUT /books/{isbn}/cover { key }
API    → S3      HEAD <key>                       ← ¿se subió de verdad?
API    → DB      books.cover_key = key
```

En la arquitectura target eso evita que subir 5 MB ocupe una tarea de ECS, y esquiva el
tope de 10 MB de payload de API Gateway.

En la base se guarda la **key** (`covers/<isbn>/<uuid>.jpg`), no la URL: la URL pública
la arma `app/storage.py` al serializar, así que mudar de bucket, de región o poner
CloudFront adelante (`S3_PUBLIC_BASE_URL`) no obliga a reescribir filas. La key lleva un
uuid para que al reemplazar una portada cambie la URL y ni el browser ni el CDN sirvan
la imagen vieja desde su cache.

Detalles que no son obvios:

- **Se valida dos veces al confirmar**: que la key sea del prefijo de ese libro (nadie
  apunta la portada a un objeto ajeno) y que el objeto exista (`HEAD`), porque si el
  `PUT` del browser falló la fila quedaría con una imagen rota.
- **Dos endpoints de S3 en local**: SigV4 firma el `Host`, así que la URL que va al
  browser se firma contra `S3_PUBLIC_ENDPOINT_URL` (`http://localhost:9000`) y las
  operaciones del servidor usan `S3_ENDPOINT_URL` (`http://storage:9000`, la red de
  compose). En AWS las dos quedan vacías y boto3 usa los endpoints de S3.
- **Sin `S3_BUCKET` la feature queda apagada**: los endpoints de portada dan 503 y el
  resto de la API funciona igual — así corre la suite de tests. `GET /health` reporta
  `storage: ok | down | disabled`.
- **Borrar es best-effort**: si falla el borrado en S3, la fila ya no apunta a esa key y
  el objeto queda huérfano para que lo limpie una lifecycle rule del bucket. La fuente
  de verdad es la base, no el bucket.

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
- **Base de datos**: DynamoDB en modo On-Demand con Point-in-Time Recovery (el tráfico
  de una red de bibliotecas es irregular), y el rol de la tarea con permisos acotados a la
  tabla y sus índices. El código ya está: en local cambia solo `DYNAMO_ENDPOINT_URL`
  (se borra en AWS) y la tabla la crea la infraestructura como código en lugar de
  `table.py`. Las tablas globales cubren la lectura de stock del resto de la red.
- **Cache**: ElastiCache for Redis en subnets privadas. El código ya está: solo
  cambia `REDIS_URL` del contenedor local al endpoint del cluster.
- **Portadas**: S3 + CloudFront. El código ya está: se borran `S3_ENDPOINT_URL` y
  `S3_PUBLIC_ENDPOINT_URL` (que apuntan a MinIO), `S3_BUCKET` pasa a ser el bucket real
  y las credenciales salen del rol de la tarea en vez del `.env`.
- **Búsqueda**: un dominio de OpenSearch sirve el listado, la búsqueda y las ciudades del
  catálogo. Lo alimenta una **Lambda** con un *event source mapping* al stream de la tabla
  (`NEW_AND_OLD_IMAGES`): es el handler de `app/indexer.py`, el mismo código que en local corre
  como el servicio `indexer`. Faltan, y son parte de la infraestructura, la DLQ y
  `BisectBatchOnFunctionError` del mapping (un evento que falla siempre congela el shard) y la
  firma SigV4 del cliente.
- **Analítica**: un proceso ETL (Glue) copia datos hacia un data warehouse
  (Redshift/Athena sobre S3), separado de la base operativa.
- **API pública**: API Gateway con autenticación, rate limiting y métricas
  para exponer el catálogo a bibliotecas externas.
- **Portal de bibliotecarios**: la API ya emite y valida sus propios JWT
  (`POST /auth/login`, HS256 con `JWT_SECRET`) y aplica roles
  `customer`/`librarian`/`sysadmin`. En la arquitectura target ese emisor lo
  reemplaza Cognito: el resto de la autorización por rol ya está en su lugar.
- **Redes**: VPC con subnets públicas (ALB/API Gateway, CloudFront) y privadas
  (VPC endpoint de DynamoDB, OpenSearch, tareas de cómputo).

## Próximos pasos

- Migrar la emisión de tokens propia a Cognito.
- Definir el pipeline ETL hacia el data warehouse. Con DynamoDB deja de ser opcional: no hay
  consultas ad-hoc sobre el modelo operativo, y la analítica sale de ahí (Glue → Athena/Redshift).
- Infraestructura como código (Terraform/CDK) para el despliegue en AWS.
