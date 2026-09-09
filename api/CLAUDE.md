# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos

Desde `api/`, con un virtualenv (Python 3.12):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # ajustar DATABASE_URL si hace falta
alembic upgrade head
uvicorn app.main:app --reload
```

Tests (pytest):

```bash
pytest                                          # toda la suite
pytest tests/test_health.py                     # un archivo
pytest tests/test_health.py::test_health -v     # un test puntual
```

Con Docker Compose (desde la raíz del repo; levanta Postgres + Redis + API + frontend):

```bash
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed      # carga datos de ejemplo
```

No hay linter ni formatter configurado en `api/` (no hay `pyproject.toml`, ruff, flake8, black, etc.).

## Arquitectura

Monolito en capas, con dependencias apuntando siempre hacia adentro:

`controllers` (routers FastAPI + esquemas Pydantic en `schemas.py`) → `services` (lógica de negocio) → `persistence/repositories` (acceso a datos, una clase por entidad) → `persistence/models.py` (ORM SQLAlchemy).

- `persistence` no conoce `services` ni FastAPI; `services` no conoce HTTP.
- Las excepciones de dominio (`NotFoundError`, `ConflictError`, `UnauthorizedError`, `ForbiddenError`, definidas en `services/errors.py`) se mapean a códigos HTTP recién en `app/main.py` vía `@app.exception_handler`.
- Cada repository recibe la `Session` de SQLAlchemy por constructor (`BookRepository(db)`, etc.); los services son funciones sueltas, no clases.

### Autorización

La regla de dónde vive cada chequeo:

- **Reglas de rol puras** → `controllers/dependencies.py` (`require_roles(...)`, `require_self_or_sysadmin`), como `Depends` del endpoint. No necesitan cargar el recurso.
- **Reglas que dependen de los datos del recurso** (p. ej. "un `librarian` solo opera sobre su propia sede") → en el service, junto a la entidad que igual hay que cargar: `_assert_can_manage` en `library_service` y `reservation_service`. Por eso esos services reciben un `editor`/`viewer` (un `User` del dominio, no nada de HTTP) y lanzan `ForbiddenError`.

`get_current_user` decodifica el JWT y recarga el `User` de la base en cada request, así que un token de un usuario borrado da 401 aunque la firma siga siendo válida.

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
- **Nunca se cachea nada que dependa del usuario del token** (`/reservations`, `/users`,
  `/auth/me`): la clave es compartida entre usuarios y filtraría datos.
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

### Modelo de datos

`app/persistence/models.py` implementa el diseño normalizado descripto en `data_base.md` (diccionario de datos con las decisiones de normalización tomadas sobre el esquema conceptual original). Puntos que no son obvios leyendo un solo archivo:

- `Book` está keyed por `isbn` (string), no por un id autoincremental.
- Autores y géneros son entidades propias (`Author`, `Genre`) vinculadas a `Book` mediante tablas intermedias N:M (`book_authors`, `book_genres`) — son `Table` de SQLAlchemy Core, no clases mapeadas, porque no tienen columnas propias más allá de la PK compuesta.
- El ciclo de vida de `PhysicalBook.status` está partido en dos: `available` y `lost` son los únicos destinos manuales (`PATCH /physical-books/{id}/status`, ver `physical_book_service.MANUAL_STATUSES`), mientras que `reserved` y `loaned` los maneja solo el flujo de reservas. `lost` se puede marcar en cualquier momento y cierra la reserva abierta que hubiera (vía `reservation_service.close_open_reservation`); volver a `available`, en cambio, solo sale de `lost`, porque liberar un ejemplar retenido es tarea de cancel/return.
- `PhysicalBook` es el ejemplar físico (referencia `Book.isbn` + `Library.id`, con su propio `status`: `available`/`reserved`/`loaned`/`lost`). Es la entidad que efectivamente se reserva, no el `Book` abstracto.
- `Reservation` vincula `User` con `PhysicalBook`; no hay un enum de estados de reserva — el ciclo de vida se resuelve con tres columnas: `picked_up` (retirado en sede) más `cancelled_at`/`returned_at`. Una reserva está **abierta** mientras ambos timestamps sean null; cerrarla es lo que libera el ejemplar. Nunca se borra la fila: cancelar, devolver y vencer marcan, para conservar el historial de préstamos. Por eso `DELETE /physical-books/{id}` da 409 ante cualquier reserva, incluso cerrada (la FK la referencia): un ejemplar que ya circuló se saca de circulación marcándolo `lost`, no borrándolo.
- `User.role` (`customer`/`librarian`/`sysadmin`) junto con `User.library_id` (nullable) determinan si es un usuario final o el bibliotecario a cargo de una sede puntual — un usuario administra a lo sumo una `Library`.
- Todas las columnas y valores de enum están en inglés por decisión explícita del equipo, aunque el diccionario de datos en `data_base.md` esté en español (p.ej. `idioma`→`language`, `nombre`→`name`, `estado`→`status`, `retirado`→`picked_up`).

### Estado conocido / desalineado

- La autenticación es un JWT propio (HS256, `pyjwt`) emitido por `POST /auth/login`, no Cognito todavía: en la arquitectura target lo reemplaza Cognito (ver README raíz, sección "De este MVP a la arquitectura en AWS"). El secreto sale de `JWT_SECRET` y tiene un default solo apto para desarrollo.
- La búsqueda de catálogo (`BookRepository.search`) usa `ILIKE` como placeholder; en la arquitectura target la reemplaza OpenSearch.
