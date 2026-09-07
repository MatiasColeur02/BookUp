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

Con Docker Compose (desde la raíz del repo; levanta Postgres + API + frontend):

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
- Las excepciones de dominio (`NotFoundError`, `ConflictError`, definidas en `services/errors.py`) se mapean a códigos HTTP recién en `app/main.py` vía `@app.exception_handler`.
- Cada repository recibe la `Session` de SQLAlchemy por constructor (`BookRepository(db)`, etc.); los services son funciones sueltas, no clases.

### Modelo de datos

`app/persistence/models.py` implementa el diseño normalizado descripto en `data_base.md` (diccionario de datos con las decisiones de normalización tomadas sobre el esquema conceptual original). Puntos que no son obvios leyendo un solo archivo:

- `Book` está keyed por `isbn` (string), no por un id autoincremental.
- Autores y géneros son entidades propias (`Author`, `Genre`) vinculadas a `Book` mediante tablas intermedias N:M (`book_authors`, `book_genres`) — son `Table` de SQLAlchemy Core, no clases mapeadas, porque no tienen columnas propias más allá de la PK compuesta.
- `PhysicalBook` es el ejemplar físico (referencia `Book.isbn` + `Library.id`, con su propio `status`: `available`/`reserved`/`loaned`/`lost`). Es la entidad que efectivamente se reserva, no el `Book` abstracto.
- `Reservation` vincula `User` con `PhysicalBook`; no hay un enum de estados de reserva — el ciclo de vida se resuelve con `expires_at` (vencimiento) + el flag booleano `picked_up` (retirado en sede).
- `User.role` (`customer`/`librarian`/`sysadmin`) junto con `User.library_id` (nullable) determinan si es un usuario final o el bibliotecario a cargo de una sede puntual — un usuario administra a lo sumo una `Library`.
- Todas las columnas y valores de enum están en inglés por decisión explícita del equipo, aunque el diccionario de datos en `data_base.md` esté en español (p.ej. `idioma`→`language`, `nombre`→`name`, `estado`→`status`, `retirado`→`picked_up`).

### Estado conocido / desalineado

- El endpoint de confirmación de reservas es `PATCH /reservations/{id}/pickup` (antes `/confirm`) y no tiene autenticación; está pensado para integrarse con Cognito en el portal de bibliotecarios (ver README raíz, sección "De este MVP a la arquitectura en AWS").
- La búsqueda de catálogo (`BookRepository.search`) usa `ILIKE` como placeholder; en la arquitectura target la reemplaza OpenSearch.
