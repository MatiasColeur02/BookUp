# Migración de PostgreSQL a DynamoDB

Plan de ejecución para reemplazar la capa de datos de BookUp por DynamoDB + OpenSearch.
No hay nada en producción: no hay migración de datos, hay **reimplementación**. El
`seed.py` sigue siendo la forma de poblar el sistema y su interfaz (`python -m app.seed`)
no cambia.

**Criterio de decisión de todo este documento**: maximizar la velocidad de lectura y usar
cada herramienta para lo que sirve. Donde había una opción más simple pero transitoria,
está anotada como *alternativa descartada* con el motivo.

---

## 1. Diagnóstico: qué está realmente acoplado

La premisa del proyecto es que la capa de datos no debería afectar a las demás. **Es cierta
para `controllers` y para el frontend, y es falsa para `services`.** Conviene tenerlo claro
antes de planificar, porque define el 70% del trabajo.

### 1.1 Los services dependen del ORM, no de los repositories

`README.md` dice que `services` conoce a `persistence`. En la práctica conoce a
**SQLAlchemy**, que es otra cosa:

| Acoplamiento | Dónde | Volumen |
|---|---|---|
| Reciben `Session` de SQLAlchemy como primer parámetro | los 8 services | 8 archivos |
| Unit-of-work: `db.commit()` / `db.refresh()` | todos los de escritura | **43 llamadas** |
| Mutación en el lugar de entidades ORM (`book.title = title`) | `catalog`, `user`, `library`, `genre`, `author`, `reservation`, `physical_book` | ~40 asignaciones |
| Navegación de relaciones lazy | `reservation_service.py:27,149,166,183,201-202`, `catalog_service.py:130-132` | 8 sitios |

El caso más claro es `reservation_service.py:149`:

```python
reservation.picked_up = True
reservation.physical_book.status = PhysicalBookStatus.loaned
db.commit()
```

Eso son **dos filas de dos tablas escritas atómicamente** por el unit-of-work, más un
`SELECT` implícito para cargar `physical_book`. DynamoDB no tiene ninguna de las tres cosas
de forma implícita: hay que pedir un `TransactWriteItems` explícito. No es un detalle de
implementación que se pueda esconder detrás del repository actual — cambia la forma del
código del service.

**Veredicto**: sí, hay algo mal diseñado, y es esto. La solución no es evitar tocar los
services, es **terminar de aislarlos**: que reciban una unidad de trabajo del repository y
no un `Session`, y que no naveguen relaciones. Después de esta migración, cambiar de motor
otra vez sería un trabajo de `persistence/` solamente.

### 1.2 El contrato HTTP asume capacidades de Postgres

| Supuesto | Dónde | Estado tras la migración |
|---|---|---|
| `id` entero autoincremental (6 entidades) | `models.py`, `schemas.py`, `openapi.yml`, `frontend/src/types.ts` | **Se preserva** con contador atómico (§4.1) |
| `limit`/`offset` + `total` exacto | `BookPage`, `catalog_controller.py` | **Se preserva** vía OpenSearch (§5) |
| `UNIQUE` en `users.email` y `genres.name` | `models.py` | **Se preserva** con ítems de unicidad (§4.4) |
| `COUNT(*)` para los 409 al borrar | 4 repositories | Se reemplaza por `Query(Limit=1)` (§4.5) |

### 1.3 Lo que no está acoplado y no se toca

`app/cache.py`, `app/ratelimit.py`, `app/storage.py`, `app/main.py` y los 8 controllers
viven en la capa HTTP y no saben qué motor hay abajo. **Se confirman como bien diseñados**:
sobreviven la migración casi intactos (§7.3).

---

## 2. Arquitectura target

```
                    ┌──────────────┐
   lecturas por     │              │  DynamoDB (tabla única `bookup`)
   clave  ─────────▶│   FastAPI    │─────▶ fuente de verdad
                    │              │       escrituras condicionales
   búsqueda y       │  (sin cambios│       transacciones
   filtros ────────▶│  en cache/   │            │
                    │   storage/   │            │ Streams
                    │  ratelimit)  │            ▼
                    │              │      ┌───────────┐
                    │              │◀─────│ Lambda    │
                    └──────────────┘      │ indexador │
                           ▲              └───────────┘
                           │                    │
                    ┌──────┴──────┐             ▼
                    │    Redis    │      ┌─────────────┐
                    │ (cache, sin │      │ OpenSearch  │
                    │   cambios)  │      │  índice de  │
                    └─────────────┘      │  catálogo   │
                                         └─────────────┘
```

**Reparto de responsabilidades:**

- **DynamoDB** — fuente de verdad de todo. Sirve todo acceso por clave conocida: detalle de
  libro, disponibilidad, ejemplares de una sede, reservas de un usuario/sede, login,
  vencimientos. Latencia de un dígito de ms.
- **OpenSearch** — proyección de solo lectura del catálogo. Sirve `GET /books` (con sus
  filtros combinables, `offset` y `total`) y `GET /books/search`. Nunca se escribe desde la
  API: solo lo alimenta el indexador.
- **DynamoDB Streams → Lambda** — único camino de indexación. Un solo camino, así el índice
  no puede divergir por un dual-write a medio aplicar.
- **Redis** — el cache actual, sin un solo cambio.

> **Alternativa descartada**: filtrar el catálogo en memoria del proceso (traer los 71
> libros con un Query y resolver filtros/orden/paginación en Python). Funciona, mantiene
> todo local y es mucho más barato, pero tiene techo en el límite de 1 MB por página de
> Query (~10.000 libros) y no es búsqueda de texto real. Es exactamente la solución
> temporal que este plan evita.

---

## 3. Modelo de datos: tabla única

Una tabla, `bookup`, con `PK` y `SK` genéricos (ambos `String`). Los nombres de los
atributos de índice también son genéricos (*index overloading*): un mismo GSI sirve varios
tipos de ítem.

### 3.1 Tipos de ítem

| Entidad | PK | SK | Atributos propios | Desnormalizado |
|---|---|---|---|---|
| Libro | `BOOK#<isbn>` | `META` | title, language, pages, synopsis, cover_key, created_at, updated_at | — |
| Libro↔Autor | `BOOK#<isbn>` | `AUTHOR#<id>` | author_id | **author_name** |
| Libro↔Género | `BOOK#<isbn>` | `GENRE#<id>` | genre_id | **genre_name** |
| Autor | `AUTHOR#<id>` | `META` | id, name | — |
| Género | `GENRE#<id>` | `META` | id, name | — |
| Sede | `LIB#<id>` | `META` | id, name, address, state, city, hours, phone, email, website | — |
| Ejemplar | `COPY#<id>` | `META` | id, isbn, library_id, status, open_reservation_id | **library_city, library_name, book_title** |
| Reserva | `RES#<id>` | `META` | id, user_id, physical_book_id, reserved_at, expires_at, picked_up, cancelled_at, returned_at | **library_id, isbn** |
| Usuario | `USER#<id>` | `META` | id, email, password_hash, name, language, role, library_id | — |
| Alias de email | `USEREMAIL#<email>` | `META` | user_id | unicidad + lookup |
| Alias de género | `GENRENAME#<name>` | `META` | genre_id | unicidad |
| Contador | `COUNTER#<entidad>` | `META` | seq | — |

**Las tres desnormalizaciones que más importan:**

1. **`author_name` / `genre_name` dentro del ítem del libro.** Es lo que convierte
   `GET /books/{isbn}` —hoy un `SELECT` más dos joins N:M sobre `book_authors` y
   `book_genres`— en **un solo `Query` con `PK = BOOK#<isbn>`** que devuelve el libro y sus
   autores y géneros juntos. Es el *adjacency list pattern*.
2. **`library_city` / `library_name` dentro del ejemplar.** Elimina el
   `joinedload(PhysicalBook.library)` de `available_by_book` y el join a `Library` de
   `available_cities`.
3. **`library_id` dentro de la reserva.** Hoy `_assert_can_manage`
   (`reservation_service.py:27`) navega `reservation.physical_book.library_id`, o sea
   carga el ejemplar solo para autorizar. Con el `library_id` copiado, **la autorización no
   necesita ninguna lectura extra**.

**`open_reservation_id` en el ejemplar** merece mención aparte: reemplaza
`get_open_for_physical_book` (hoy un `SELECT` con dos `IS NULL`) por un puntero directo. Un
ejemplar tiene a lo sumo una reserva abierta, así que es un campo, no un índice.

### 3.2 Índices secundarios globales

| Índice | PK | SK | Qué resuelve |
|---|---|---|---|
| **GSI1** *(listados ordenados)* | `CATALOG` / `AUTHORS` / `GENRES` / `LIBRARIES` / `USERS` | `<name>#<id>` | `list_all()` de autores, géneros, sedes, usuarios — ya ordenados alfabéticamente, sin ordenar en memoria |
| **GSI2** *(hijos de X)* | `AUTHOR#<id>` / `GENRE#<id>` / `BOOK#<isbn>` / `USER#<id>` / `COPY#<id>` | según tipo | libros de un autor/género, ejemplares de un libro, reservas de un usuario o de un ejemplar |
| **GSI3** *(por sede)* | `LIB#<id>` | `COPY#<status>#<isbn>#<id>` o `RES#<reserved_at>#<id>` | `list_physical_books(library_id=, status=)` y `list_reservations(library_id=)` |
| **GSI4** *(sparse, reservas abiertas)* | `OPEN` | `<expires_at>#<id>` | `list_expired` y `is_open=true` |

**GSI2 sobre ejemplares** usa `SK = <status>#LIB#<library_id>#<id>`. Eso hace que
`available_by_book` sea un `Query` con `begins_with(SK, "available#")`: **los ejemplares
disponibles de un libro salen ya agrupados por sede y ordenados**, sin filtrar en memoria y
sin leer los prestados ni los perdidos.

**GSI4 es sparse y ahí está la gracia**: el atributo `GSI4PK` se escribe con el valor
`OPEN` al crear la reserva y **se elimina del ítem** (`REMOVE GSI4PK, GSI4SK`) al cerrarla.
Un ítem sin el atributo no existe en el índice, así que el índice contiene **solo las
reservas abiertas** — que son decenas, no las ~190 históricas ni las miles que habrá.
`list_expired` (`reservation_repository.py:44`) pasa de recorrer la tabla de reservas a un
`Query` acotado con `SK < now`.

### 3.3 Por qué no multi-tabla

Con una tabla por entidad, armar un `BookOut` son 3 round-trips (libro, autores, géneros) y
`available_by_book` son 2 (ejemplares, sedes). La tabla única los baja a 1 y 1. Como el
objetivo declarado es velocidad de lectura, no hay discusión.

---

## 4. Los cuatro problemas que Postgres resolvía gratis

### 4.1 IDs autoincrementales

Un ítem contador por entidad, incrementado atómicamente:

```python
resp = table.update_item(
    Key={"PK": f"COUNTER#{entity}", "SK": "META"},
    UpdateExpression="ADD seq :one",
    ExpressionAttributeValues={":one": 1},
    ReturnValues="UPDATED_NEW",
)
return int(resp["Attributes"]["seq"])
```

`ADD` es atómico en el servidor: dos altas concurrentes nunca obtienen el mismo número.

**Costo**: una escritura extra por alta y una partición caliente por entidad. Irrelevante
acá — las altas son operaciones de staff, raras, y **las lecturas no tocan el contador**,
que es lo que se quiere escalar.

**Beneficio**: `id: number` se mantiene en `openapi.yml`, `schemas.py` y
`frontend/src/types.ts`. **El frontend no se toca.**

> **Alternativa descartada**: ULID/UUID. Es lo idiomático en DynamoDB y evita el contador,
> pero cambia `id: integer` a `string` en el contrato, y el requisito es no afectar al
> frontend.

### 4.2 Transacciones: la reserva

Hoy (`reservation_service.py:80-93`) es leer-y-después-escribir, seguro solo porque la
transacción de Postgres lo cubre. En DynamoDB **eso es una condición de carrera**: dos
usuarios leen `available` y ambos reservan. La versión correcta no lee: **condiciona la
escritura**.

```python
table.meta.client.transact_write_items(TransactItems=[
    {"Update": {
        "Key": {"PK": f"COPY#{copy_id}", "SK": "META"},
        "UpdateExpression": "SET #s = :reserved, open_reservation_id = :rid",
        "ConditionExpression": "#s = :available",      # <-- el candado
        ...
    }},
    {"Put": {"Item": reservation_item}},
])
```

`TransactionCanceledException` con razón `ConditionalCheckFailed` se traduce al
`ConflictError` que ya existe, y `main.py` lo mapea al mismo 409 de hoy. **El contrato HTTP
no cambia.**

Las cinco transiciones que necesitan `TransactWriteItems` (ejemplar + reserva juntos):

| Operación | Condición | Efecto |
|---|---|---|
| `create_reservation` | `status = available` | `→ reserved`, crea reserva, setea `GSI4PK` |
| `mark_picked_up` | `picked_up = false` y abierta | `→ loaned`, `picked_up = true` |
| `cancel_reservation` | abierta y `picked_up = false` | `→ available`, `cancelled_at`, **REMOVE GSI4PK** |
| `mark_returned` | abierta y `picked_up = true` | `→ available`, `returned_at`, **REMOVE GSI4PK** |
| `update_status(lost)` | — | `→ lost` + cierra la reserva abierta si hay |

**Nota importante**: las condiciones que hoy son `if` en el service pasan a ser
`ConditionExpression`. Eso no es solo traducción — es **más correcto que hoy**, porque hoy
el `if` y el `commit` están separados por microsegundos en los que otro request puede
colarse. La migración cierra una carrera que ya existía.

**Límite a respetar**: `TransactWriteItems` admite hasta 100 ítems y no puede tocar el
mismo ítem dos veces. `expire_reservations` puede vencer más de 100 reservas de un saque,
así que se procesa **en lotes**, no en una transacción única. Sigue siendo idempotente:
la condición "sigue abierta" hace que una segunda corrida no encuentre nada.

### 4.3 El renombre de un autor

Es el precio de la desnormalización, y hay que decirlo explícito: `PATCH /authors/{id}`
deja de ser un `UPDATE` de una fila.

```
1. Query GSI2  PK=AUTHOR#<id>            -> los N libros que lo tienen
2. TransactWriteItems por lotes de 100   -> author_name en cada BOOK#<isbn>/AUTHOR#<id>
3. Update      PK=AUTHOR#<id> SK=META    -> el nombre canónico
4. (Streams reindexa esos N libros en OpenSearch, automático)
```

**Es aceptable** por tres razones: los renombres son excepcionales, ya invalidaban el
namespace entero del cache (`author_controller` invalida `NS_CATALOG`), y el beneficio —un
round-trip en cada lectura del catálogo, que es el 90% del tráfico— se cobra en cada
request. Lo mismo aplica a géneros y a la ciudad de una sede.

### 4.4 Unicidad (`users.email`, `genres.name`)

DynamoDB no tiene `UNIQUE` salvo en la clave primaria. El patrón es crear un **ítem de
unicidad** cuya PK *es* el valor único, en la misma transacción que la entidad:

```python
transact_write_items(TransactItems=[
    {"Put": {"Item": {"PK": f"USEREMAIL#{email}", "SK": "META", "user_id": new_id},
             "ConditionExpression": "attribute_not_exists(PK)"}},   # <-- el UNIQUE
    {"Put": {"Item": user_item}},
])
```

Si el email ya existe, la transacción entera falla y `create_user` levanta el `ConflictError`
que ya levanta hoy. **Bonus**: el mismo ítem resuelve `get_by_email` (el login) con un
`GetItem` directo, sin GSI y con lectura fuerte.

Al borrar un usuario o cambiar un email hay que borrar/mover el alias en la misma
transacción. Está en el checklist de §9.

### 4.5 Los `COUNT(*)` de los 409

`count_books`, `count_physical_books` y `count_reservations` existen solo para preguntar
"¿hay al menos uno?" (`if repo.count_books(author_id): raise ConflictError`). Contar en
DynamoDB es recorrer; preguntar si existe uno es un `Query` con `Limit=1`.

**Cambio de interfaz**: `count_books()` → `has_books()`, `count_physical_books()` →
`has_physical_books()`, `count_reservations()` → `has_reservations()`. Los services cambian
solo el nombre de la llamada.

---

## 5. Búsqueda y filtros: OpenSearch

Es la parte que DynamoDB no hace y ninguna desnormalización arregla: los filtros de
`GET /books` son **combinables entre sí** (`?genre_id=1&genre_id=2&city=Rosario&q=borges`).
Servirlos con copias exigiría un ítem por combinación —53 autores × 16 géneros × 10
ciudades— y el texto libre ni siquiera se enumera.

### 5.1 El documento

`_id` = ISBN. Un documento por libro, construido por el indexador:

```json
{
  "isbn": "9780307474728", "title": "Cien años de soledad",
  "language": "es", "pages": 417, "synopsis": "...", "cover_key": "covers/...",
  "authors": [{"id": 1, "name": "Gabriel García Márquez"}],
  "genres":  [{"id": 1, "name": "Ficción"}, {"id": 2, "name": "Novela"}],
  "available_cities": ["Buenos Aires", "Rosario"],
  "available_copies": 7
}
```

**`available_cities` dentro del documento del libro es la decisión clave.** Sin eso, el
filtro `?city=` (que significa "con ejemplar disponible hoy ahí") viviría en DynamoDB y el
resto en OpenSearch, y habría que intersecar dos motores en la aplicación. Con el campo
adentro, `?genre_id=1&city=Rosario` es **una sola query**. El costo es que cada reserva
reindexa un documento: son cientos por día, nada.

### 5.2 Las consultas

| Endpoint | Consulta |
|---|---|
| `GET /books` | `bool.must: multi_match(q)` + `bool.filter: terms(authors.id) / terms(genres.id) / terms(available_cities)`, `sort: title.keyword`, `from`/`size`, `track_total_hits: true` |
| `GET /books/search` | `multi_match` sobre `title^3, authors.name^2, isbn, synopsis` |
| `GET /books/cities` | agregación `terms` sobre `available_cities` |

`track_total_hits: true` es lo que hace que `BookPage.total` siga siendo **exacto**, y
`from`/`size` mapean 1:1 a `offset`/`limit`. **El contrato de paginación no cambia y el
frontend no se entera.**

La semántica actual —OR dentro de un filtro, AND entre filtros
(`book_repository.py:_filters`)— se preserva: `terms` es OR interno, y cada cláusula del
`filter` es AND.

### 5.3 Seguridad

`_like_pattern` (el escapado de `%` y `_`) desaparece con el `ILIKE`. Su equivalente es
**usar `multi_match` y nunca `query_string`**: `query_string` interpreta operadores del
usuario (`*`, `AND`, `~`) y permite armar consultas carísimas a propósito. `multi_match`
trata la entrada como texto. El tope de `MAX_QUERY_LENGTH = 200` del controller se mantiene.

### 5.4 El indexador

Lambda suscrita al stream de la tabla. Para cada evento, determina el ISBN afectado y
reindexa ese documento completo:

| Evento | ISBN afectado |
|---|---|
| `BOOK#<isbn>` (META, AUTHOR#, GENRE#) | directo |
| `COPY#<id>` (alta, baja, cambio de status) | del atributo `isbn` del ejemplar |
| `AUTHOR#`/`GENRE#`/`LIB#` META | **ninguno directamente** — el renombre ya reescribe los ítems desnormalizados, y esos eventos disparan la reindexación |

Que el renombre cascadee solo es consecuencia directa de haber desnormalizado: el indexador
no necesita saber qué libros tiene un autor, porque el evento le llega por cada libro.

**Reindexado**: `python -m app.reindex` recorre la tabla y reconstruye el índice entero.
Necesario para bootstrap, tras el seed, y ante cualquier sospecha de divergencia. El índice
es **descartable por definición**: la fuente de verdad es DynamoDB.

---

## 6. Estructura de archivos

```
api/app/persistence/
  dynamo.py          NUEVO  cliente boto3, recurso de tabla, get_db()
  keys.py            NUEVO  constructores de PK/SK/GSI (un solo lugar que sabe el formato)
  entities.py        NUEVO  dataclasses + enums (reemplaza models.py)
  table.py           NUEVO  creación de tabla y GSIs (reemplaza alembic)
  search.py          NUEVO  cliente OpenSearch (lecturas del catálogo)
  repositories/             REESCRITOS — misma interfaz pública
  models.py          BORRAR
  database.py        BORRAR
api/alembic/         BORRAR  (junto con alembic.ini)
api/app/indexer.py   NUEVO  handler del stream (corre como Lambda; en local, un poller)
api/app/reindex.py   NUEVO  reindexado completo
```

`keys.py` centralizado no es cosmético: el formato de las claves es el contrato interno de
la tabla única, y disperso por 7 repositories se desincroniza al primer cambio.

---

## 7. Cambios capa por capa

### 7.1 `persistence` — reescritura completa

`models.py` → `entities.py`, con **dataclasses** en vez de clases ORM. `UserRole` y
`PhysicalBookStatus` se mudan tal cual (siguen siendo `str, Enum`). `Reservation.is_open`
sigue siendo una `@property` con la misma lógica.

Los 7 repositories conservan **exactamente su interfaz pública** salvo los tres `count_*`
de §4.5. Lo que cambia es que ahora **persisten de verdad**: hoy `create()` hace `add` +
`flush` y el commit lo da el service; en DynamoDB `create()` escribe y punto.

### 7.2 `services` — el trabajo grueso

Los 8 archivos se tocan. El patrón de cambio es mecánico:

| Hoy | Después |
|---|---|
| `def create_author(db: Session, *, name)` | `def create_author(db: Dynamo, *, name)` — **misma firma**, otro tipo |
| `db.commit()` / `db.refresh(x)` | se eliminan (43 sitios) |
| `author.name = name` + `db.commit()` | `repo.update(author_id, name=name)` → devuelve la entidad nueva |
| `reservation.physical_book.library_id` | `reservation.library_id` (desnormalizado) |
| `reservation.physical_book.status = X` + `commit` | `repo.transition(...)` con `TransactWriteItems` |
| `if physical_book.status != available: raise` | `ConditionExpression` + traducir la excepción |

Que la firma `(db, *, ...)` se mantenga es deliberado: **los controllers siguen escribiendo
`db = Depends(get_db)` y no cambian una línea por esto.**

Lo que **no** cambia en los services: toda la autorización (`_assert_can_manage`,
`_assert_can_view`, `_assert_open`), todas las reglas de dominio (`MANUAL_STATUSES`, el
ciclo de vida de la reserva, `_validate_role_and_library`) y todas las excepciones de
`errors.py`. Es lógica de negocio pura y es agnóstica del motor — ahí el diseño en capas sí
cumplió.

### 7.3 `controllers`, `cache`, `ratelimit`, `storage`, `main` — casi intactos

- **`cache.py`, `ratelimit.py`, `storage.py`**: **cero cambios.** Trabajan sobre payloads
  Pydantic ya serializados y sobre Redis/S3. Ni se enteran.
- **`main.py`**: solo `GET /health`, que suma `search: ok | down` junto a `cache` y
  `storage`, con el mismo criterio (informativo, no baja el status general).
- **Los 8 controllers**: cambia el import de `..persistence.database import get_db` a
  `..persistence.dynamo import get_db`, y el type hint `Session` → `Dynamo`. Nada más.
- **`schemas.py`**: una línea — el import de `PhysicalBookStatus` y `UserRole` pasa de
  `models` a `entities`. `from_attributes=True` funciona igual sobre dataclasses, así que
  `BookOut.from_book()` y el resto quedan como están.

**Sí hay que actualizar un comentario, y no es menor**: `_text()` en `schemas.py` documenta
que los `max_length` "replican el ancho de las columnas de `models.py`". DynamoDB no tiene
ancho de columna, así que **la justificación cambia aunque los números no**: los topes pasan
a ser límites de dominio puros, más el techo de 400 KB por ítem. Los límites **se
mantienen todos** — siguen siendo lo correcto — pero el comentario que explica por qué
existen queda desactualizado, y ese comentario es lo que evita que alguien los borre.
Lo mismo con la nota de `CLAUDE.md` sobre `StringDataRightTruncation`.

### 7.4 `seed.py` — se mantiene, se reescribe por dentro

**La interfaz no cambia**: `python -m app.seed`, dataset determinista con
`random.Random(20240501)`, mismos 10 sedes / 71 libros / 53 autores / 16 géneros / ~400
ejemplares / ~190 reservas, misma password `bookup123`, misma guarda de idempotencia.

Qué cambia adentro:

| Hoy | Después |
|---|---|
| `Base.metadata.create_all(bind=engine)` | `table.ensure_table()` (crea tabla + 4 GSIs, espera a que estén `ACTIVE`) |
| `db.query(models.Library).count() > 0` | `GetItem` de un ítem centinela `SEED#META` |
| `db.add_all(...)` + `db.flush()` para obtener ids | ids del contador (§4.1), después `BatchWriteItem` de a 25 |
| `copy.status = models.PhysicalBookStatus.loaned` | el estado se escribe en el ítem al construirlo |
| `db.commit()` final | los batches ya escribieron |

**Dos cosas nuevas y obligatorias en el seed:**

1. Escribir los ítems desnormalizados (`author_name` en cada `BOOK#/AUTHOR#`, `library_city`
   en cada `COPY#`, `library_id` en cada `RES#`). Si el seed los omite, el sistema arranca
   con datos inconsistentes.
2. **Dejar los contadores en el valor correcto** después de insertar. Si el seed crea 53
   autores escribiendo ids 1..53 a mano pero deja `COUNTER#author` en 0, el primer
   `POST /authors` devuelve el id 1 y **pisa a García Márquez**. Es el bug más fácil de
   introducir en toda la migración.

El seed **no** indexa en OpenSearch directamente: escribe en DynamoDB y después llama a
`reindex`. Un solo camino de indexación, también acá.

### 7.5 Tests — 209 tests, el mismo contrato

La suite prueba la API por HTTP (`TestClient`), no los repositories, así que **la enorme
mayoría no cambia**. Lo que cambia son los fixtures de `conftest.py`:

| Fixture | Hoy | Después |
|---|---|---|
| `engine` | SQLite in-memory + `create_all` | tabla en **DynamoDB Local**, nombre único por test, borrada al final |
| `db_session` | `sessionmaker` | recurso de tabla apuntando a ese nombre |
| `client` | override de `get_db` | igual, override del `get_db` nuevo |
| `make_user` | `db_session.add` + `commit` | `UserRepository(db).create(...)` |
| — | — | **nuevo**: `FakeSearchIndex` en proceso, espejando el `FakeRedis` de `test_cache.py` |

`pytest` pasa a necesitar Docker (`amazon/dynamodb-local`), a diferencia de hoy. Es el
precio de testear contra el motor real: escrituras condicionales, transacciones canceladas
y consistencia eventual de GSIs son justo lo que hay que probar, y son lo que un mock no
reproduce fielmente.

**Tests nuevos que la migración obliga a escribir:**

- Dos reservas concurrentes sobre el mismo ejemplar → una 201, una 409.
- El contador no repite ids bajo concurrencia.
- Alta con email duplicado → 409 (ahora vía transacción, no vía constraint).
- Renombrar un autor propaga el nombre a todos sus libros.
- Cerrar una reserva la saca del índice sparse (`list_expired` no la ve).
- `expire_reservations` con más de 100 vencidas (el límite de la transacción).

### 7.6 Infraestructura y configuración

**`docker-compose.yml`**: `db: postgres:16` → `amazon/dynamodb-local`; se suma
`opensearchproject/opensearch` (single-node, security plugin apagado) y un servicio
one-shot `db-init` que crea tabla e índice — mismo patrón que el `storage-init` que ya
existe para MinIO. El comando de `api` deja de correr `alembic upgrade head`.

**`config.py`**: `database_url` se va; entran `dynamo_table`, `dynamo_endpoint_url` (vacío
en AWS, como ya se hace con `s3_endpoint_url`), `aws_region`, `opensearch_url`,
`opensearch_index`. Se mantiene el criterio de que **vacío = apagado** que ya usan
`redis_url` y `s3_bucket`.

**`requirements.txt`**: fuera `sqlalchemy`, `alembic`, `psycopg2-binary`; entra
`opensearch-py`. `boto3` ya está.

**En AWS**: tabla en modo **On-Demand** (el tráfico de una red de bibliotecas es irregular y
On-Demand evita dimensionar a ojo), Point-in-Time Recovery activado, y el rol de la tarea
ECS con permisos acotados a esa tabla y sus índices. El indexador es una Lambda con
`event source mapping` al stream (`NEW_AND_OLD_IMAGES`) y una **DLQ**: un evento que falla
sistemáticamente bloquea el shard entero y congela el índice.

---

## 8. Fases de ejecución

Cada fase deja el repo en un estado verificable. Las fases 1-3 se pueden hacer sin romper
nada de lo que existe.

| # | Fase | Entregable | Listo cuando |
|---|---|---|---|
| **1** ✅ | Infra local | `docker-compose` con DynamoDB Local + OpenSearch, `dynamo.py`, `keys.py`, `table.py` | `docker compose up` levanta todo y `ensure_table()` crea tabla y 4 GSIs |
| **2** | Entidades | `entities.py` con las dataclasses y los enums | `schemas.py` importa de ahí y `pytest` sigue en verde con Postgres |
| **3** ✅ | Repositories | los 7 reescritos + tests de repositorio propios (nuevos) | cada método probado contra DynamoDB Local |
| **4** ✅ | Services | los 8 migrados, incluidas las 5 transacciones de §4.2 | los tests de reserva/ejemplar en verde, incluidos los de concurrencia |
| **5** ✅ | Seed | `seed.py` reescrito, con contadores y desnormalización | `python -m app.seed` dos veces = mismo resultado, sin duplicar |
| **6** ✅ | OpenSearch | `search.py`, `indexer.py`, `reindex.py`, los 3 endpoints migrados | `GET /books` con filtros combinados devuelve lo mismo que con Postgres |
| **7** ✅ | Limpieza | borrar `models.py`, `database.py`, `alembic/`, dependencias | `grep -r sqlalchemy api/` no devuelve nada |
| **8** | Docs | `README.md`, `CLAUDE.md`, `openapi.yml` (sin cambios de contrato, sí de notas) | las secciones de §10 actualizadas |

> **Fase 1 hecha.** Desvíos respecto del plan, todos a propósito: los servicios del compose
> se llaman `dynamodb` / `dynamodb-init` (no `db-init`) porque `db` sigue siendo Postgres
> hasta la fase 7; DynamoDB Local queda en el puerto 8001 del host (el 8000 es la API);
> `dynamodb-init` crea solo la tabla, el índice de OpenSearch llega con la fase 6; la
> tabla nace con el stream `NEW_AND_OLD_IMAGES` ya prendido. Además `keys.py` agrega el
> ítem de enlace `COPY#<id>` / `RES#<id>` (`keys.copy_reservation`): el `GSI2` de una
> reserva ya está tomado por su usuario, y "¿este ejemplar tuvo reservas?" (el 409 de
> `DELETE /physical-books`) necesita una partición por ejemplar. Se escribe en la misma
> transacción que la reserva (fase 4). Los tests de `table.py` corren contra DynamoDB
> Local y se saltean solos si no hay uno.

> **Fase 3 hecha.** Los repositories nuevos viven en `persistence/repositories/` (los
> de SQLAlchemy siguen en `repositories/` hasta la fase 4; en la 7 se borra el viejo y se
> mueve este). Desvíos y decisiones:
>
> - **Errores propios de persistencia** (`persistence/errors.py`): `persistence` no puede
>   importar `ConflictError` de `services`. Levanta `ConditionFailedError` /
>   `AlreadyExistsError`, `main.py` los mapea a 409 como red de seguridad, y un service que
>   quiera un mensaje propio los atrapa. La traducción de boto3 sigue estando en un solo
>   lugar (`_support.run_transaction`), como pide §9.
> - **Las 5 transiciones de §4.2 ya están** en `ReservationRepository` (`create`,
>   `mark_picked_up`, `cancel`, `mark_returned`, `expire`) y en
>   `PhysicalBookRepository.update_status(lost)`, con sus tests de concurrencia. La fase 4
>   queda en cablear los services y en los tests HTTP.
> - `update(id, **cambios)` en cada repository (un `None` borra el atributo) reemplaza a la
>   mutación en el lugar; `count_*` → `has_*`.
> - **Omitidos a propósito**: `BookRepository.list_filtered/search/available_cities` (van a
>   OpenSearch en la fase 6), `list_all/count_all` del libro y `AuthorRepository.get_by_name`
>   (ningún service los usa y DynamoDB no tiene índice por nombre).
> - **Dos listas nuevas en GSI1** (`COPIES`, `RESERVATIONS`): sin ellas, `GET /physical-books`
>   y `GET /reservations` de un sysadmin sin filtros serían un Scan de la tabla.
> - El renombre de autor/género escribe primero el nombre canónico y después cascadea (no al
>   revés, como decía §4.3): un nombre de género repetido tiene que fallar *antes* de tocar
>   ningún libro. Repetir el update completa una cascada interrumpida.
> - `TransactWriteItems` pide `TableName` en **cada** operación (el ejemplo de §4.2 lo omite);
>   `run_transaction` lo completa.
> - Las lecturas de la tabla base son fuertes; las de GSI no pueden serlo, así que
>   `has_books`/`has_physical_books`/`available_by_book` pueden ir unos ms atrás en AWS.

> **Fase 4 hecha — punto de no retorno cruzado.** Los 8 services, los controllers y los
> fixtures de la suite hablan solo con DynamoDB. Qué hay que saber:
>
> - **Los repositories nuevos ya son `persistence/repositories/`**: se borró el paquete
>   SQLAlchemy y `dynamo_repositories/` ocupó su lugar (no esperé a la fase 7: quedaba
>   código muerto con el mismo nombre). `models.py`, `database.py` y `alembic/` siguen,
>   solo para el `seed.py` viejo, hasta las fases 5 y 7.
> - **`GET /books` con filtros, `/books/search` y `/books/cities` corren sobre un puente en
>   memoria** (`repositories/_catalog_bridge.py`): un Scan del catálogo filtrado en Python.
>   Es la "alternativa descartada" de §2, usada a propósito como andamio para que la suite
>   de catálogo siga en verde entre la fase 4 y la 6. **No escala** (sirve para el seed de
>   71 libros) y se borra entero con OpenSearch. Diferencia visible: el texto ya no tiene
>   comodines, `%` y `_` son literales.
> - **La app arranca vacía hasta la fase 5**: el `seed.py` viejo escribe en Postgres. Hasta
>   entonces se puede registrar un usuario y probar, pero no hay catálogo ni sysadmin.
> - **`pytest` ahora necesita DynamoDB Local** y **falla** (no se saltea) si no lo encuentra:
>   una suite que se saltea sola es una suite en verde que no probó nada. Cada test tiene su
>   propia tabla (4 GSIs) y la borra al terminar; la suite pasó de ~2 a ~3,5 minutos.
> - **La traducción de errores quedó en cada service**: atrapan `ConditionFailedError` /
>   `AlreadyExistsError` del repository y relanzan el `ConflictError` con su mensaje de
>   siempre. Las lecturas previas ("¿está disponible?") ya solo dan mensajes precisos; el
>   candado real es la condición de la escritura. `physical_book_service` dejó de depender
>   de `reservation_service` (cerrar la reserva de un ejemplar perdido ahora es del repo).
> - `docker-compose`: la API espera a `dynamodb-init` (`service_completed_successfully`).

> **Fase 5 hecha.** `python -m app.seed` siembra DynamoDB: mismo dataset (10 sedes, 53 autores,
> 16 géneros, 71 libros, 398 ejemplares, 193 reservas, 32 usuarios), mismo RNG, misma password.
> Qué hay que saber:
>
> - **Formato de ítems compartido**: nuevo `repositories/_items.py` con cómo se ve cada entidad
>   en la tabla (campos desnormalizados incluidos). Lo usan los repositories y el seed, así no
>   hay dos copias del formato que se desincronicen.
> - **Contadores en N + centinela al final.** El seed deja `COUNTER#*` en el último id usado
>   (el primer `POST /authors` da el 54 y no pisa a García Márquez; hay test de cada entidad) y
>   escribe `SEED#META` último, así una corrida interrumpida se puede repetir.
> - **Se niega a mezclarse**: si la tabla tiene contadores pero no centinela (alguien usó la
>   API sin sembrar), falla con `SeedConflictError` en vez de pisar `USER#1`.
> - **Escribe en paralelo** (8 lotes de 25 a la vez): DynamoDB Local persistente tarda ~0,7 s
>   por escritura y sembrar en serie eran 35–120 s.
> - **No indexa en OpenSearch**: eso será `app.reindex` (fase 6), que se llama después del seed.
> - **Nuevo servicio `dynamodb-test`** (DynamoDB Local *en memoria*, puerto 8002) para `pytest`:
>   la suite pasó de 3,5 a ~2 minutos y ya no toca la tabla `bookup` con tus datos. La suite
>   necesita `docker compose up -d dynamodb-test`.
> - La fecha de las reservas es relativa a "ahora"; `seed(now=...)` la fija para los tests.
>   Lo único que no es idéntico entre corridas es el hash bcrypt de los passwords (sal nueva).

> **Fase 6 hecha.** `GET /books` (con filtros), `/books/search` y `/books/cities` salen de
> OpenSearch; el puente en memoria de la fase 4 se borró. Qué hay que saber:
>
> - **Piezas**: `persistence/search.py` (cliente, mapping, documento y `multi_match`),
>   `app/indexer.py` (handler de Lambda + poller local sobre el stream) y `app/reindex.py`.
>   El servicio `indexer` del compose engancha el stream, reindexa todo y sigue los cambios, así
>   `docker compose up` deja la búsqueda andando; el seed también reindexa. Retraso medido de
>   punta a punta: ~1 s (reservar, cancelar, renombrar un autor, crear un libro).
> - **La imagen del evento corrige a GSI2.** Los disponibles de un libro se leen de un índice
>   secundario (eventualmente consistente), así que el estado que trae el propio evento pisa lo
>   que diga el índice; si no, «se reservó el último ejemplar» podía dejar a la ciudad ofreciendo
>   stock hasta el próximo evento del libro.
> - **Orden refrescar → invalidar.** El indexador fuerza el refresco del índice *antes* de
>   invalidar el cache de catálogo. Al revés (como estaba al principio), una lectura dentro de la
>   ventana de ~1 s recacheaba la lista vieja por 5 minutos. Lo encontró la prueba de punta a punta.
> - **Búsqueda de texto**: `multi_match` tipo `bool_prefix` con `and`: todas las palabras, y solo
>   la última puede estar a medias («borg» sí, «jor luis borges» no; «Ficc\*» tampoco: con un
>   carácter después ya no es palabra a medias). Sin tildes ni mayúsculas. Es menos permisiva que
>   el `ILIKE '%…%'`, que matcheaba en medio de una palabra. Los operadores del usuario (`*`, `OR`,
>   `~`, `title:`) son texto.
> - **El índice faltante no es un error**: sin índice (aún nadie indexó) el catálogo es vacío.
>   Sin `OPENSEARCH_URL` o con el servicio caído, los tres endpoints dan **503** con `Retry-After`,
>   y `/health` informa `search: ok|down|disabled` sin bajar el status general.
> - **Tests**: la suite HTTP usa un `FakeSearchIndex` en proceso; `test_search_contract.py` corre
>   las mismas ~100 expectativas contra el fake **y** contra OpenSearch real (si el fake promete
>   algo que el motor no hace, falla ahí). `test_indexer.py` incluye un recorrido completo sobre
>   el stream real de DynamoDB Local. Un fixture de sesión impide que un test llegue al índice de
>   desarrollo por accidente. `pytest` ahora también necesita `docker compose up -d search`.
> - **Reset de la tabla**: el poller detecta que la tabla se recreó (stream nuevo) y vuelve a
>   reindexar solo; no hace falta reiniciar el servicio.
> - **Pendiente de IaC (fase fuera del plan)**: la Lambda necesita su DLQ y
>   `BisectBatchOnFunctionError`, y el cliente falta firmar con SigV4 para un dominio gestionado de
>   AWS; en local no aplica y no está probado.
> - `opensearch-py` 2.7.1 entra a `requirements.txt`. Además el servicio `search` del compose
>   desactiva el umbral de disco: con el disco de la VM de Docker casi lleno, OpenSearch grababa un
>   bloqueo de creación de índices en el volumen que sobrevivía a liberar espacio.

> **Fase 7 hecha.** Borrados `models.py`, `database.py`, `alembic/` y `alembic.ini`; fuera
> `sqlalchemy`, `alembic` y `psycopg2-binary` de `requirements.txt` (la imagen ya no los instala);
> fuera `database_url` de `config.py`, y fuera el servicio `db` (Postgres), su volumen y el
> `alembic upgrade head` del compose. `grep -rniE "sqlalchemy|alembic|psycopg" api/` no devuelve
> nada en el código; solo quedan menciones en la documentación, que es la fase 8. Quedan en tu
> Docker el volumen viejo `bookup_bookup_db_data` (datos de Postgres, ya sin uso): se borra con
> `docker volume rm`. Además:
>
> - **Suite más rápida y estable**: cada test creaba y borraba una tabla de 4 GSIs, y DynamoDB Local
>   en memoria se degrada con tantas altas y bajas (la suite llegó a tardar 3,5 veces más). Ahora
>   hay una tabla compartida por sesión que se **vacía** entre tests (`db`), y una tabla propia
>   (`isolated_db`) solo para los que miran el stream o la borran. Si la suite se pone lenta,
>   `docker compose restart dynamodb-test`.
> - Los comentarios que hablaban de Postgres o del ORM como estado actual se reescribieron
>   (`entities.py`, `repositories/__init__.py`, `schemas.py`, `cache.py`, los tests).

**El punto de no retorno es la fase 4.** Hasta la 3 conviven los dos mundos; a partir de ahí
los services solo hablan DynamoDB.

**Orden de validación sugerido dentro de cada fase**: primero las entidades sin relaciones
(Author, Genre, Library), después Book con su adjacency list, después PhysicalBook, y al
final Reservation, que es la que concentra las transacciones.

---

## 9. Riesgos y trampas

| Riesgo | Por qué duele | Mitigación |
|---|---|---|
| **Contadores desincronizados tras el seed** | El primer `POST` pisa una entidad sembrada | Test explícito: sembrar, crear uno por API, verificar que el id es `N+1` |
| **`GET /books` eventualmente consistente** | Tras `POST /books` el libro tarda ~1 s en aparecer en el listado | Aceptado. El POST devuelve la entidad desde DynamoDB (lectura fuerte), así que la pantalla que acaba de crearlo ya la tiene |
| **Desnormalización desfasada** | Un renombre a medio propagar deja nombres viejos | `TransactWriteItems` por lotes + `reindex` como herramienta de reparación |
| **Alias de unicidad huérfanos** | Borrar un usuario sin borrar `USEREMAIL#` bloquea ese email para siempre | Borrado en la misma transacción, y test que verifica que el email se puede reusar |
| **Reserva con `ConditionalCheckFailed` mal traducido** | Un 500 donde el contrato dice 409 | Traducción centralizada en el repository, no en cada service |
| **Lambda del indexador con poison pill** | Un evento que falla bloquea el shard y congela el índice | DLQ + `bisect_on_function_error` + alarma |
| **Ítem de 400 KB** | Un libro con cientos de autores no entra | No aplica hoy (los ítems `AUTHOR#` son separados, no un array), pero el `synopsis` de 5.000 caracteres se mantiene acotado |
| **Costo de OpenSearch** | Un dominio gestionado no es gratis ni se apaga | Decisión tomada bajo el criterio de "no algo temporal". Vale dejar dimensionado el mínimo viable |

**Lo que se pierde y no se recupera:**

- **Consultas ad-hoc.** No hay `psql` para preguntar algo que no se modeló. Toda pregunta
  nueva necesita un GSI o un scan. Para analítica, el camino es el ETL a Redshift/Athena
  que el README ya contempla — ahora deja de ser opcional.
- **Integridad referencial declarativa.** Las FKs desaparecen: nada impide un `COPY#` que
  apunte a un `BOOK#` borrado salvo los chequeos de §4.5. La lógica que hoy garantiza el
  motor pasa a estar en `services`, y depende de que esté bien escrita.
- **Migraciones versionadas.** No hay `alembic upgrade head`. Cambiar la forma de un ítem es
  un backfill escrito a mano. `table.py` crea la tabla, pero no versiona su evolución.

---

## 10. Documentación a actualizar (fase 8)

| Archivo | Qué |
|---|---|
| `README.md` | Stack, estructura del árbol, "Cómo correrlo local" (sin alembic), la tabla de cache (el motivo del TTL de `/books/search` cambia: ya no es un ILIKE sin índice), y la sección "De este MVP a la arquitectura en AWS" — OpenSearch deja de ser "próximo paso" |
| `api/CLAUDE.md` | Comandos (sin alembic), "Modelo de datos" entero, la nota de `StringDataRightTruncation` en validación, "Inyección SQL" → `multi_match` vs `query_string`, y "Estado conocido" |
| `api/openapi.yml` | **Sin cambios de contrato.** Sí, notas sobre la consistencia eventual de `GET /books` |
| `api/data_base.md` | El diccionario de datos normalizado sigue siendo el modelo **conceptual**; agregar la tabla de acceso→ítem de §3 como el modelo **físico** |
| `frontend/` | **Nada.** Es el objetivo del plan y §4.1 y §5.2 son lo que lo hace cierto |

---

## 11. Resumen de impacto

| Capa | Impacto | Motivo |
|---|---|---|
| `frontend/` | **Ninguno** | Los ids siguen siendo enteros y la paginación sigue siendo `offset`/`total` |
| `openapi.yml` | **Ninguno en el contrato** | Mismos endpoints, mismos tipos, mismos códigos |
| `controllers/` | **1 import + 1 type hint** por archivo | Nunca supieron del motor. Diseño validado |
| `cache/ratelimit/storage` | **Ninguno** | Idem |
| `schemas.py` | **1 import** (+ comentarios) | `from_attributes` funciona igual sobre dataclasses |
| `services/` | **Los 8, sustancial** | Dependían del unit-of-work de SQLAlchemy, no de los repositories |
| `persistence/` | **Reescritura completa** | Es el objetivo |
| `seed.py` | **Reescritura interna, misma interfaz** | Requisito explícito |
| `tests/` | **Fixtures + ~6 tests nuevos** | Los 209 prueban HTTP, no el motor |

**La conclusión que vale para el informe**: el proyecto acertó en aislar HTTP de los datos
—`controllers`, `cache`, `ratelimit` y `storage` cruzan la migración sin tocarse— y falló en
aislar el dominio del ORM: los `services` recibían un `Session` y usaban su unit-of-work. La
migración es la oportunidad de cerrar eso, y el criterio para saber si quedó bien cerrado es
concreto: **cuando termine, un tercer cambio de motor debería tocar solo `persistence/`.**
