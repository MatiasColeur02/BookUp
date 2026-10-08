# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos

La API necesita **DynamoDB** (y OpenSearch para el catálogo con filtros), así que se desarrolla con Docker Compose desde la raíz del repo:

```bash
docker compose up --build                       # DynamoDB Local, OpenSearch, Redis, MinIO, API, indexador, frontend
docker compose exec api python -m app.seed      # datos de ejemplo (idempotente; reindexa el catálogo)
docker compose exec api python -m app.reindex   # reconstruye el índice de búsqueda desde DynamoDB
```

`docker compose up` crea la tabla (`dynamodb-init`) y deja corriendo el `indexer`, que crea el índice, lo llena y sigue el stream. No hay migraciones: la forma de la tabla la define `app/persistence/table.py`. Para empezar de cero: borrar la tabla (`app.persistence.table.drop_table`) y volver a correr `python -m app.persistence.table` y el seed; el indexador detecta solo que la tabla se recreó.

Tests (pytest). Necesitan DynamoDB Local en memoria y OpenSearch, y **fallan** —no se saltean— si no los encuentran:

```bash
docker compose up -d dynamodb-test search
docker compose run --rm --no-deps api pytest                                   # toda la suite
docker compose run --rm --no-deps api pytest tests/test_catalog.py            # un archivo
docker compose run --rm --no-deps api pytest tests/test_catalog.py::test_get_book -v   # un test
```

Desde el host (con un virtualenv de Python 3.12 y `pip install -r requirements-dev.txt`) los endpoints por defecto son `http://localhost:8002` (`DYNAMO_TEST_ENDPOINT_URL`) y `http://localhost:9200` (`OPENSEARCH_URL`). La suite usa `dynamodb-test` —una instancia en memoria, aparte de la de desarrollo— y nunca toca la tabla `bookup` con tus datos. Si DynamoDB Local en memoria se degrada y la suite se pone lenta, `docker compose restart dynamodb-test`.

No hay linter ni formatter configurado en `api/` (no hay `pyproject.toml`, ruff, flake8, black, etc.).

## Arquitectura

Monolito en capas, con dependencias apuntando siempre hacia adentro:

`controllers` (routers FastAPI + esquemas Pydantic en `schemas.py`) → `services` (lógica de negocio) → `persistence/repositories` (acceso a datos, una clase por entidad) → `persistence/dynamo.py`, `keys.py` y `entities.py` (cliente, formato de claves y entidades).

- `persistence` no conoce `services` ni FastAPI; `services` no conoce HTTP.
- Las excepciones de dominio (`NotFoundError`, `ConflictError`, `UnauthorizedError`, `ForbiddenError`, definidas en `services/errors.py`) se mapean a códigos HTTP recién en `app/main.py` vía `@app.exception_handler`.
- `persistence` tiene sus propios errores (`persistence/errors.py`) porque no puede importar los de `services`: `ConditionFailedError` / `AlreadyExistsError` (una escritura condicional perdió la carrera) y `SearchUnavailableError`. Un service que quiere un mensaje propio los atrapa y relanza el `ConflictError` de siempre; si nadie los atrapa, `main.py` los mapea igual (409 y 503).
- Cada repository recibe un `Dynamo` (`persistence/dynamo.py`: el recurso de la tabla y el cliente de bajo nivel) por constructor (`BookRepository(db)`, etc.); los services son funciones sueltas `(db, *, ...)`, no clases. **Los services no ven boto3, claves ni transacciones**: no hay unidad de trabajo, `create`/`update`/`delete` escriben de verdad y cada uno es atómico. Un cambio de motor tocaría solo `persistence/`.
- Las entidades (`persistence/entities.py`) son dataclasses **inmutables**: para cambiar una, `repo.update(id, campo=valor)` devuelve la nueva (un valor `None` borra el atributo). Los `count_*` no existen: las preguntas «¿hay al menos uno?» son `has_*` (contar en DynamoDB es recorrer).

### Autorización

La regla de dónde vive cada chequeo:

- **Reglas de rol puras** → `controllers/dependencies.py` (`require_roles(...)`, `require_self_or_sysadmin`), como `Depends` del endpoint. No necesitan cargar el recurso.
- **Reglas que dependen de los datos del recurso** (p. ej. "un `librarian` solo opera sobre su propia sede") → en el service, junto a la entidad que igual hay que cargar: `_assert_can_manage` en `library_service` y `reservation_service`. La reserva lleva copiada la `library_id` del ejemplar, así que autorizar no necesita leer el ejemplar. Por eso esos services reciben un `editor`/`viewer` (un `User` del dominio, no nada de HTTP) y lanzan `ForbiddenError`.

`get_current_user` decodifica el JWT y recarga el `User` de la base en cada request, así que un token de un usuario borrado da 401 aunque la firma siga siendo válida.

### Validación de entrada y límites

La regla es que **ningún valor del cliente llegue a la base sin un techo**. Vive en
`controllers/schemas.py` porque es validación de payload, no de dominio.

- **Los `max_length` de los esquemas son límites de dominio puros** (el helper `_text(...)`
  deja el número al lado del campo). DynamoDB no tiene ancho de columna que los imponga, pero
  siguen siendo lo correcto: sin ellos un cliente escribe megabytes por campo, un ítem se pasa
  del tope de 400 KB de DynamoDB y sale un **500** en lugar de un 422, y el mismo tope viaja
  al documento de OpenSearch y a la UI. El frontend repite los números en
  `frontend/src/lib/limits.ts`. Al agregar un campo de texto, agregar su tope; no borrar los
  existentes por «no hay columna».
- **Los opcionales usan `min_length=0`**: el frontend manda `""` para vaciar un campo.
  Los obligatorios usan `min_length=1` con `strip_whitespace`, así `"   "` no es nombre.
- **Lo que no tiene columna que lo acote lleva un límite de dominio**: `pages` (1 a
  50.000), `synopsis` (un `Text`, sin tope en la base), `expires_at` de una reserva (a lo
  sumo 365 días: futuro no alcanza, un vencimiento lejano retiene el ejemplar).
- **La contraseña se corta en 72 bytes** porque es todo lo que mira bcrypt: aceptar más
  sería truncar en silencio y hacer que dos contraseñas distintas abran la misma cuenta.
- **Los parámetros de lectura también** (`catalog_controller`): largo del texto de
  búsqueda, y `max_length` sobre las listas para acotar cuántas veces se repite un filtro.
- **Inyección**: no hay SQL; los datos van a DynamoDB como valores tipados. El texto libre del
  catálogo va a OpenSearch como `multi_match` y **nunca como `query_string`**: este último
  interpreta operadores del usuario (`*`, `AND`, `~`, `campo:`) y permite armar consultas
  carísimas a propósito, mientras `multi_match` trata la entrada como texto. Es el reemplazo del
  escapado de `%` y `_` que hacía el `ILIKE`. El tope de `MAX_QUERY_LENGTH` (200) se mantiene.
- **Techo del cuerpo del request** (`main.py`, middleware): 1 MB por `Content-Length`,
  antes de leerlo. Las portadas no cuentan, van directo a S3.
- **Portadas**: el `size` del pedido de firma es una *declaración*; el tamaño y el tipo
  reales se verifican con un `HEAD` al confirmar la key, y lo que no cumple se borra del
  bucket antes de tocar la fila.

### Rate limiting

`app/ratelimit.py`, sobre el mismo Redis que el cache y con el mismo criterio de capas
(vive en `controllers`; `services` no sabe que existe) y de fallas (**fail-open**: si
Redis no contesta se deja pasar, porque un nodo caído no puede dejar a todo el mundo
afuera del login).

- Ventana fija con `INCR` + `EXPIRE`, atómico y O(1).
- **Login**: un contador por IP *antes* de autenticar —comparar un hash de bcrypt es caro
  por diseño, así que ese chequeo es lo que frena el gasto de CPU— y otro por cuenta
  contando **solo los intentos fallidos**, *después*. El orden no es un detalle: con el
  chequeo por cuenta hecho antes, cualquiera dejaba al dueño afuera errándole diez veces
  la contraseña. Contando solo fallos, la contraseña correcta siempre entra.
- **Auto-registro**: por IP. `POST /users/staff` no se frena, ya pide token de sysadmin.

### Cache

`app/cache.py` cachea las lecturas públicas en Redis (ElastiCache en AWS). Vive en
`controllers`, no en `services`: lo que se guarda son payloads JSON ya serializados por
los esquemas Pydantic, no entidades ORM — que no son serializables y lazy-loadean fuera
de la sesión. La regla de capas se mantiene: `services` y `persistence` no saben del
cache, igual que no saben de HTTP.

- **Uso**: `cache.cached(namespace, key, ttl=..., model=..., loader=...)` en los GET, y
  `cache.invalidate(*namespaces)` después del service en los POST/PATCH/DELETE.
- **Invalidación por generaciones**: cada namespace tiene un contador `bookup:ver:<ns>`
  embebido en la clave; invalidar es un `INCR`. Nunca usar `KEYS`/`SCAN` para barrer, que
  en ElastiCache bloquea el nodo.
- **Qué namespaces tocar en una escritura** lo dicta cómo se embeben los esquemas, no
  qué tabla se escribió: `BookOut` embebe autores y géneros, y `BookAvailability` embebe
  `BookOut` y `LibraryOut`. Cada controller tiene su tupla `_WRITE_NAMESPACES` con el
  motivo comentado. Al agregar un endpoint cacheado, revisar quién más embebe ese
  esquema.
- **El namespace depende de los datos, no del endpoint**: `GET /books` cae en
  `NS_CATALOG` normalmente, pero con filtro `city` pasa a `NS_AVAILABILITY` (y a su TTL
  corto), porque "en esta ciudad" significa "con ejemplar disponible hoy" y eso cambia
  con cada reserva. Mismo criterio para `GET /books/cities`.
- **Nunca se cachea nada que dependa del usuario del token** (`/reservations`, `/users`,
  `/auth/me`): la clave es compartida entre usuarios y filtraría datos.
- **El indexador también invalida**: cuando el índice de búsqueda cambia, `app/indexer.py` invalida
  `NS_CATALOG` y `NS_AVAILABILITY`, **después** de forzar el refresco del índice. Sin eso, una
  lectura entre la escritura y su indexación (~1 s) cachearía la lista vieja por 5 minutos.
- **Fail-open**: todo error de Redis se traga y se sirve desde la base, con un breaker de
  10 s. Sin `REDIS_URL` el cache queda apagado; así corre la suite de tests, que usa un
  `FakeRedis` propio en `tests/test_cache.py`.

### Portadas (S3)

`app/storage.py` maneja las portadas de libros sobre almacenamiento de objetos (S3 en
AWS, MinIO en `docker-compose`). Vive en `controllers` por la misma razón que el cache:
`services` y `persistence` no saben que existe.

- **La imagen no pasa por la API**: `POST /books/{isbn}/cover-upload` devuelve una URL
  firmada, el browser hace el `PUT` directo al bucket y `PUT /books/{isbn}/cover`
  confirma la key. El service solo escribe la columna (`catalog_service.set_cover`) y
  devuelve la key anterior para que el controller borre el objeto huérfano.
- **En la base va la key, no la URL** (`Book.cover_key`): la URL pública la arma
  `storage.public_url` al serializar. Por eso *todo* endpoint que devuelva libros tiene
  que construir el esquema con `BookOut.from_book(book)`: validar la entidad ORM directo
  deja `cover_url` en `None`.
- `cover_url` es un campo normal y no un `computed_field` a propósito: el payload viaja
  por el cache, y al revalidar el JSON cacheado no hay `cover_key` del que recalcularla.
- **Dos endpoints**: SigV4 firma el `Host`, así que lo que se firma para el browser usa
  `S3_PUBLIC_ENDPOINT_URL` y lo que hace el servidor (`head`/`delete`) usa
  `S3_ENDPOINT_URL`. En AWS ambas quedan vacías.
- **Fail-safe**: sin `S3_BUCKET` la feature queda apagada (503 en los endpoints de
  portada, el resto de la API igual); los borrados son best-effort y no pueden voltear
  una request. Así corre la suite, que stubea `presign_upload`/`exists`/`delete`.

### Modelo de datos y persistencia

La base es **DynamoDB, tabla única `bookup`**, más un índice de **OpenSearch** para el catálogo. El diseño relacional normalizado (`data_base.md`, secciones 1 a 3) sigue siendo el modelo *conceptual*; la sección 4 de ese documento es el modelo *físico* (tipos de ítem, GSIs, cómo se resuelve cada acceso). Puntos que no son obvios leyendo un solo archivo:

- **`keys.py` es el único lugar que conoce el formato de las claves** (`PK`/`SK` y los 4 GSIs). Los repositories piden las claves de un ítem a una función de ahí y nunca arman `"BOOK#..."` a mano; la forma de cada ítem está en `repositories/_items.py`, que usan tanto los repositories como el seed.
- **Desnormalización**: el ítem del libro lleva `author_name`/`genre_name`, el ejemplar `library_city`/`library_name`/`book_title`, la reserva `library_id`/`isbn`. Renombrar un autor, un género, una sede o un libro **cascadea** a esos ítems (por lotes de 100, idempotente). Si agregás un campo copiado, agregá su cascada.
- **Ids enteros** (el contrato HTTP no cambió) con un ítem `COUNTER#<entidad>` incrementado con `ADD` (atómico). `Book` se identifica por ISBN. **El seed deja los contadores en el último id**: si no, el primer `POST` pisa un registro sembrado.
- **Unicidad** (`users.email`, `genres.name`) con ítems *alias* escritos con `attribute_not_exists(PK)` en la misma transacción. Borrar un usuario o cambiar su email mueve el alias; si no, el email queda bloqueado para siempre.
- **El estado de la reserva y del ejemplar se escriben juntos**, en un `TransactWriteItems` **condicionado** (`ReservationRepository` y `PhysicalBookRepository.update_status`): reservar, retirar, cancelar, devolver, vencer y marcar perdido. Condicionan en vez de leer-y-escribir (`status = available`, «sigue abierta», `open_reservation_id = <esta reserva>`); el candado contra la carrera es la condición. Los services igual leen antes, **solo para dar un mensaje preciso**; no es lo que garantiza la consistencia. `TransactWriteItems` pide `TableName` en cada operación (lo completa `run_transaction`), admite hasta 100 ítems y no puede tocar el mismo ítem dos veces.
- El ciclo de vida de `PhysicalBook.status` está partido en dos: `available` y `lost` son los únicos destinos manuales (`PATCH /physical-books/{id}/status`, ver `physical_book_service.MANUAL_STATUSES`), mientras que `reserved` y `loaned` los maneja solo el flujo de reservas. `lost` se puede marcar en cualquier momento y cierra la reserva abierta que hubiera (en la misma transacción); volver a `available`, en cambio, solo sale de `lost`, porque liberar un ejemplar retenido es tarea de cancel/return.
- `PhysicalBook` es el ejemplar físico (referencia `Book.isbn` + `Library.id`, con su propio `status`: `available`/`reserved`/`loaned`/`lost`). Es la entidad que efectivamente se reserva, no el `Book` abstracto. Un ejemplar tiene a lo sumo una reserva abierta: `open_reservation_id` es un puntero, no un índice.
- `Reservation` vincula `User` con `PhysicalBook`; no hay un enum de estados — el ciclo de vida se resuelve con tres campos: `picked_up` (retirado en sede) más `cancelled_at`/`returned_at` (ausentes mientras no ocurren). Una reserva está **abierta** mientras ambos estén ausentes; cerrarla es lo que libera el ejemplar. Nunca se borra el ítem: cancelar, devolver y vencer marcan, para conservar el historial. Por eso `DELETE /physical-books/{id}` da 409 ante cualquier reserva, incluso cerrada (el ítem de enlace `COPY#<id>/RES#<id>` la registra): un ejemplar que ya circuló se saca de circulación marcándolo `lost`, no borrándolo.
- **GSI4 es disperso**: solo contiene las reservas abiertas. Cerrar una reserva hace `REMOVE GSI4PK, GSI4SK`; si un camino nuevo cierra reservas y no lo hace, `list_expired` va a seguir viéndolas.
- `User.role` (`customer`/`librarian`/`sysadmin`) junto con `User.library_id` (opcional) determinan si es un usuario final o el bibliotecario a cargo de una sede puntual — un usuario administra a lo sumo una `Library`.
- Todos los atributos y valores de enum están en inglés por decisión explícita del equipo, aunque el diccionario de datos en `data_base.md` esté en español (p.ej. `idioma`→`language`, `nombre`→`name`, `estado`→`status`, `retirado`→`picked_up`).
- **Lecturas**: las de la tabla base son fuertes (lo que se acaba de escribir se lee). Los GSI no admiten lecturas fuertes, así que `has_books`, `has_physical_books` y `available_by_book` pueden ir unos ms atrás en AWS.

### Búsqueda del catálogo (OpenSearch)

`GET /books` (con filtros), `/books/search` y `/books/cities` salen de `persistence/search.py`, no de DynamoDB. El índice es **una proyección de solo lectura y descartable**:

- **Un solo camino de escritura**: la API nunca escribe en el índice. Lo hace `app/indexer.py` (una Lambda con un event source mapping al stream de la tabla en AWS; en local, un poller que corre como el servicio `indexer` del compose), que por cada evento determina el ISBN afectado y reconstruye *ese documento entero* desde DynamoDB. Reconstruir en vez de aplicar el delta lo hace idempotente. `python -m app.reindex` lo rearma completo (bootstrap, sospecha de divergencia, reparación de una cascada interrumpida).
- **La imagen del evento corrige al GSI**: los disponibles de un libro se leen de un índice secundario eventualmente consistente, así que el estado que trae el propio evento pisa lo que diga.
- **`available_cities` va dentro del documento del libro**, para que `genre_id=1&city=Rosario` sea una sola query.
- **Eventualmente consistente** (~1 s). `GET /books/{isbn}` y las respuestas de los `POST`/`PATCH` leen de DynamoDB y no sufren esto; el listado sí. Un test que crea datos y luego lista el catálogo tiene que sincronizar el índice a mano (`sync_search`).
- **Falla aislada**: sin `OPENSEARCH_URL` o con el servicio caído, esos tres endpoints dan **503** con `Retry-After`; el resto de la API sigue. Un índice que todavía no existe es un catálogo vacío, no un error. `GET /health` informa `search: ok | down | disabled`.
- **Texto libre**: `multi_match` tipo `bool_prefix` con `and` (todas las palabras, solo la última puede estar a medias), sin distinguir mayúsculas ni tildes. El mapping es `strict`: un campo que no conoce es un bug del indexador.

### Tests

`tests/conftest.py` da una tabla `bookup` vacía por test (`db`, una tabla compartida de la sesión que se vacía entre tests; `isolated_db` crea una propia, para los tests que miran el stream o la borran) y `make`, un `Factory` (`tests/factories.py`) para armar estado pasando por los repositories. El índice de búsqueda es un `FakeSearchIndex` en proceso (autouse); `tests/test_search_contract.py` corre las mismas expectativas contra el fake y contra OpenSearch real para que el fake no mienta. Un fixture de sesión impide que un test llegue por accidente al índice de desarrollo.

### Estado conocido / desalineado

- La autenticación es un JWT propio (HS256, `pyjwt`) emitido por `POST /auth/login`, no Cognito todavía: en la arquitectura target lo reemplaza Cognito (ver README raíz, sección "De este MVP a la arquitectura en AWS"). El secreto sale de `JWT_SECRET` y tiene un default solo apto para desarrollo.
- **Falta, y es trabajo de infraestructura (no hay IaC todavía)**: la DLQ y `BisectBatchOnFunctionError` del event source mapping de la Lambda del indexador (un evento que falla siempre congela el shard), y la firma SigV4 del cliente de OpenSearch para un dominio gestionado de AWS (en local no aplica y no está probado). En AWS la tabla se crea por IaC con PITR activado, no con `table.py`.
- `table.py` no versiona: si la tabla existe con otros índices, `ensure_table()` falla en vez de repararla. Cambiar la forma de un ítem o un GSI es un backfill escrito a mano.
- El README raíz menciona `frontend/ROADMAP.md`, que no existe en el repo.
