# Arquitectura de Base de Datos - BookUp

Este documento describe el modelo de datos de la plataforma BookUp en dos niveles:

*   **Modelo conceptual (secciones 1 a 3)**: el diseño relacional normalizado. Es el que define *qué* entidades, atributos y relaciones existen, y sigue siendo la referencia para entender el dominio (por ejemplo, para el Data Warehouse analítico proyectado). Los tipos de las tablas de la sección 3 son los de un motor relacional como PostgreSQL y son **conceptuales**: ya no hay ninguna base relacional en el sistema.
*   **Modelo físico (sección 4)**: cómo se guarda eso de verdad, en **DynamoDB** (tabla única) más un índice de **OpenSearch** para el catálogo. Es el que implementa `api/app/persistence/`.

Se parte del esquema conceptual inicial y se aplican principios de normalización para asegurar la integridad, la escalabilidad y un rendimiento óptimo en las búsquedas. Las columnas y los valores de enum del código están en inglés por decisión del equipo (`idioma`→`language`, `nombre`→`name`, `estado`→`status`, `retirado`→`picked_up`), aunque este diccionario esté en español.

---

## 1. Análisis del Modelo Inicial

El esquema conceptual plantea cinco entidades principales que reflejan correctamente el dominio del problema:
*   **USERS**: Maneja la identidad de los usuarios y establece mediante el campo `admin-library` una relación con la biblioteca que administran.
*   **RESERVAS**: Entidad transaccional que vincula a un usuario con un libro físico, manejando el ciclo de vida del préstamo (fechas y estado de retiro).
*   **BOOK**: Catálogo abstracto que contiene la metadata universal del libro (ISBN, título, sinopsis, etc.).
*   **BOOK Fisico**: Representa el inventario real (la copia tangible) que reside en una biblioteca específica y posee un estado de disponibilidad.
*   **Library**: Catálogo de las distintas sedes que componen la red nacional.

---

## 2. Modificaciones y Mejoras Recomendadas

Para garantizar que el sistema soporte miles de consultas concurrentes y mantenga la integridad de los datos, se introducen las siguientes optimizaciones sobre el diseño original:

### A. Normalización de Atributos Multivaluados (Autores y Géneros)
En la entidad `BOOK`, los campos `generos` y `autores` son plurales. Almacenar múltiples valores en un solo campo (como un string separado por comas) dificulta las búsquedas cruzadas (ej. "buscar todos los libros de ciencia ficción de Isaac Asimov"). 
*   **Solución**: Extraer `Autores` y `Géneros` a tablas independientes y crear tablas intermedias (`Book_Author` y `Book_Genre`) para establecer relaciones Muchos-a-Muchos (N:M).

### B. Clarificación de Claves Primarias y Foráneas en Reservas
La entidad `RESERVAS` requiere una clave primaria propia (`id`). Además, la flecha en el diagrama apunta desde `RESERVAS` hacia `BOOK Fisico`, pero el campo se llama `id_book`. 
*   **Solución**: Renombrar el campo a `id_book_fisico` para que quede explícito que un usuario reserva **una copia específica** en una biblioteca particular, no el concepto abstracto del ISBN.

### C. Gestión de Roles y Permisos (El supuesto del Administrador)
El diagrama incluye el supuesto: *"Un usuario puede ser únicamente admin de una SOLA library"*. El campo `admin-library` en `USERS` maneja esto. 
*   **Solución**: Estandarizar este campo como `library_id` (Clave Foránea hacia `Library`, que permite valores nulos). Además, se agrega un campo `role` para diferenciar si un usuario es un ciudadano común (`CLIENTE`) o personal de la biblioteca (`BIBLIOTECARIO`). Si el rol es `BIBLIOTECARIO`, el campo `library_id` indicará qué biblioteca administra.

### D. Trazabilidad (Auditoría)
*   **Solución**: Agregar campos `created_at` y `updated_at` en todas las tablas clave para mantener un registro temporal de cuándo se crean o modifican los registros, fundamental para el Data Warehouse analítico proyectado.

---

## 3. Diccionario de Datos Refinado

A continuación, se detalla la estructura final de las entidades del modelo conceptual. Para cómo se guardan en DynamoDB, ver la sección 4.

### 3.1 Entidades Principales

#### Tabla: `users`
Administra las credenciales y perfiles tanto de usuarios finales como del personal de bibliotecas.
| Columna | Tipo de Dato (PostgreSQL) | Restricciones | Descripción |
| :--- | :--- | :--- | :--- |
| `id` | UUID / SERIAL | PRIMARY KEY | Identificador único del usuario. |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | Correo electrónico usado para login. |
| `password_hash` | VARCHAR(255) | NOT NULL | Contraseña encriptada (ej. bcrypt). |
| `nombre` | VARCHAR(150) | NOT NULL | Nombre completo. |
| `idioma` | VARCHAR(10) | DEFAULT 'es' | Preferencia de idioma (ej. 'es', 'en'). |
| `role` | VARCHAR(50) | NOT NULL | Enum: 'CLIENTE', 'BIBLIOTECARIO', 'SYSADMIN'. |
| `library_id` | UUID / INT | FK, NULLABLE | ID de la biblioteca si el usuario es BIBLIOTECARIO. Nulo para CLIENTES. |

#### Tabla: `libraries` (Sedes)
Representa cada una de las bibliotecas de la red.
| Columna | Tipo de Dato | Restricciones | Descripción |
| :--- | :--- | :--- | :--- |
| `id` | UUID / SERIAL | PRIMARY KEY | Identificador de la sede. |
| `nombre` | VARCHAR(150) | NOT NULL | Nombre de la biblioteca. |
| `direccion` | VARCHAR(255) | NOT NULL | Dirección física. |
| `provincia` | VARCHAR(100) | NOT NULL | Provincia o estado. |
| `ciudad` | VARCHAR(100) | NOT NULL | Ciudad de radicación. |
| `horarios` | VARCHAR(255) | | Horario de atención al público. |
| `telefono` | VARCHAR(50) | | Número de contacto. |
| `email` | VARCHAR(255) | | Correo de la sede. |
| `sitio_web` | VARCHAR(255) | | URL de la página de la biblioteca. |

#### Tabla: `books` (Catálogo Universal)
Metadata del libro independiente de su ubicación física.
| Columna | Tipo de Dato | Restricciones | Descripción |
| :--- | :--- | :--- | :--- |
| `isbn` | VARCHAR(13) | PRIMARY KEY | ISBN del libro (estándar internacional). |
| `titulo` | VARCHAR(255) | NOT NULL | Título de la obra. |
| `idioma` | VARCHAR(50) | NOT NULL | Idioma en que está escrito. |
| `paginas` | INTEGER | | Cantidad de páginas. |
| `sinopsis` | TEXT | | Resumen descriptivo. |

#### Tabla: `physical_books` (Inventario / Copias)
Las copias reales que existen en cada biblioteca.
| Columna | Tipo de Dato | Restricciones | Descripción |
| :--- | :--- | :--- | :--- |
| `id` | UUID / SERIAL | PRIMARY KEY | ID interno del ejemplar físico. |
| `isbn` | VARCHAR(13) | FK, NOT NULL | Refiere a `books.isbn`. |
| `library_id` | UUID / INT | FK, NOT NULL | Refiere a `libraries.id`. |
| `estado` | VARCHAR(50) | NOT NULL | Enum: 'DISPONIBLE', 'RESERVADO', 'PRESTADO', 'EXTRAVIADO'. |

#### Tabla: `reservations` (Transacciones)
Registro histórico y activo de reservas de usuarios sobre ejemplares.
| Columna | Tipo de Dato | Restricciones | Descripción |
| :--- | :--- | :--- | :--- |
| `id` | UUID / SERIAL | PRIMARY KEY | Identificador de la transacción. |
| `user_id` | UUID / INT | FK, NOT NULL | Usuario que realiza la reserva. |
| `physical_book_id` | UUID / INT | FK, NOT NULL | El ejemplar específico reservado. |
| `fecha_reserva` | TIMESTAMP | DEFAULT NOW() | Cuándo se realizó la reserva. |
| `vencimiento_reserva` | TIMESTAMP | NOT NULL | Fecha límite para ir a buscarlo. |
| `retirado` | BOOLEAN | DEFAULT FALSE | True si el usuario ya lo buscó en la sede. |

### 3.2 Entidades de Normalización (N:M)

#### Tablas: `authors` y `genres`
| Tabla | Columnas principales |
| :--- | :--- |
| **authors** | `id` (PK), `nombre` (VARCHAR NOT NULL) |
| **genres** | `id` (PK), `nombre` (VARCHAR NOT NULL UNIQUE) |

#### Tablas Intermedias: `book_authors` y `book_genres`
| Tabla | Columnas principales |
| :--- | :--- |
| **book_authors** | `isbn` (FK), `author_id` (FK) — (Ambas forman la PK compuesta) |
| **book_genres** | `isbn` (FK), `genre_id` (FK) — (Ambas forman la PK compuesta) |

---

## 4. Modelo Físico: DynamoDB + OpenSearch

El modelo relacional de arriba **no se implementa tal cual**. Se eligió DynamoDB como fuente de verdad (lecturas por clave en un dígito de milisegundos, escalado sin dimensionar) y OpenSearch para lo que DynamoDB no sabe hacer: filtros combinables más texto libre sobre el catálogo. Esta sección es el mapa entre los dos mundos. El código que la implementa es `app/persistence/keys.py` (formato de claves, único lugar que lo conoce), `repositories/_items.py` (forma de cada ítem) y `table.py` (creación de la tabla).

```
                      ┌───────────┐  escrituras condicionales / transacciones
   API (FastAPI) ───▶ │ DynamoDB  │  fuente de verdad: tabla única `bookup`
        │             └─────┬─────┘
        │ listado,          │ Streams (NEW_AND_OLD_IMAGES)
        │ búsqueda          ▼
        │             ┌───────────┐       ┌────────────────┐
        └───────────▶ │ OpenSearch│ ◀──── │ indexador      │  único camino de escritura
          (solo       └───────────┘       │ (Lambda/poller)│  al índice
           lectura)                       └────────────────┘
```

### 4.1 Tabla única: tipos de ítem

Una tabla, `bookup`, con `PK` y `SK` genéricos (ambos `String`) y modo On-Demand. Los nombres de los atributos de los índices también son genéricos (*index overloading*): un mismo GSI sirve a varios tipos de ítem. Los ids siguen siendo **enteros** (los da un contador, 4.4); los libros se identifican por ISBN.

| Entidad | `PK` | `SK` | Atributos propios | Desnormalizado |
| :--- | :--- | :--- | :--- | :--- |
| Libro | `BOOK#<isbn>` | `META` | `isbn`, `title`, `language`, `pages`, `synopsis`, `cover_key`, `created_at`, `updated_at` | — |
| Libro↔Autor | `BOOK#<isbn>` | `AUTHOR#<id>` | `author_id` | **`author_name`** |
| Libro↔Género | `BOOK#<isbn>` | `GENRE#<id>` | `genre_id` | **`genre_name`** |
| Autor | `AUTHOR#<id>` | `META` | `id`, `name` | — |
| Género | `GENRE#<id>` | `META` | `id`, `name` | — |
| Sede | `LIB#<id>` | `META` | `id`, `name`, `address`, `state`, `city`, `hours`, `phone`, `email`, `website` | — |
| Ejemplar | `COPY#<id>` | `META` | `id`, `isbn`, `library_id`, `status`, `open_reservation_id` | **`library_name`, `library_city`, `book_title`** |
| Reserva | `RES#<id>` | `META` | `id`, `user_id`, `physical_book_id`, `reserved_at`, `expires_at`, `picked_up`, `cancelled_at`, `returned_at` | **`library_id`, `isbn`** |
| Enlace ejemplar→reserva | `COPY#<id>` | `RES#<id>` | — | — |
| Usuario | `USER#<id>` | `META` | `id`, `email`, `password_hash`, `name`, `language`, `role`, `library_id` | — |
| Alias de email | `USEREMAIL#<email>` | `META` | `user_id` | unicidad y login |
| Alias de género | `GENRENAME#<name>` | `META` | `genre_id` | unicidad |
| Contador | `COUNTER#<entidad>` | `META` | `seq` | — |
| Marca del seed | `SEED` | `META` | `seeded_at` | — |

Los atributos con valor nulo **no se guardan**: un atributo ausente es el null. Por eso «reserva abierta» se expresa como `attribute_not_exists(cancelled_at) AND attribute_not_exists(returned_at)`.

**Las desnormalizaciones que más importan** (las tres que convierten un join en una lectura por clave):

1.  `author_name` / `genre_name` dentro del ítem del libro: `GET /books/{isbn}` es **un solo `Query`** con `PK = BOOK#<isbn>` que devuelve el libro y sus autores y géneros juntos (*adjacency list*).
2.  `library_city` / `library_name` dentro del ejemplar: la disponibilidad por sede no necesita ir a buscar la sede.
3.  `library_id` dentro de la reserva: la autorización de un bibliotecario (¿es de su sede?) no necesita leer el ejemplar.

El precio es que **renombrar** un autor, un género o una sede, o cambiar el título de un libro, reescribe los ítems que lo copian (por lotes de 100, idempotente: repetir la operación termina una cascada interrumpida). Es aceptable porque son operaciones excepcionales frente a cientos de miles de lecturas.

### 4.2 Índices secundarios globales

| Índice | `PK` | `SK` | Qué resuelve |
| :--- | :--- | :--- | :--- |
| **GSI1** (listados ordenados) | `CATALOG` / `AUTHORS` / `GENRES` / `LIBRARIES` / `USERS` / `COPIES` / `RESERVATIONS` | nombre plegado + `#` + id (o el id con padding) | Listar autores, géneros, sedes, usuarios ya ordenados alfabéticamente, y listar todos los ejemplares o reservas sin filtro |
| **GSI2** (hijos de X) | `AUTHOR#<id>` / `GENRE#<id>` / `BOOK#<isbn>` / `USER#<id>` | según tipo | Libros de un autor o género (`BOOK#<isbn>`), ejemplares de un libro por estado y sede (`<status>#LIB#<sede>#<id>`), reservas de un usuario (`RES#<reserved_at>#<id>`) |
| **GSI3** (por sede) | `LIB#<id>` | `COPY#<status>#<isbn>#<id>` o `RES#<reserved_at>#<id>` | Ejemplares y reservas de una sede |
| **GSI4** (disperso) | `OPEN` | `<expires_at>#<id>` | Solo las reservas **abiertas**; vencimientos |

Detalles que importan:

*   **Ordenar por nombre** usa el nombre plegado (sin tildes ni mayúsculas), para que «Álvaro» no quede después de «Zapata».
*   **Los ids llevan padding** (`0000000042`) en las sort keys, porque una SK se compara como string; en las partition keys no, porque solo se compara por igualdad.
*   **GSI2 sobre ejemplares** pone el estado primero: los disponibles de un libro salen con `begins_with(SK, "available#")`, ya agrupados por sede, sin leer los prestados ni los perdidos.
*   **GSI4 es disperso**: el atributo `GSI4PK` se escribe al crear la reserva y se **elimina** (`REMOVE GSI4PK, GSI4SK`) al cerrarla. Un ítem sin el atributo no existe en el índice, que contiene solo las reservas abiertas (decenas) y no el historial (miles). `list_expired` es un `Query` acotado, no un recorrido.
*   **El enlace ejemplar→reserva** existe porque el `GSI2` de una reserva ya está ocupado por su usuario (un ítem tiene una sola `GSI2PK`). Responde «¿este ejemplar tuvo alguna reserva?» —el 409 al borrar un ejemplar— con un `Query` de la partición `COPY#<id>`, y como es la tabla base la lectura es fuerte.
*   Los GSI tienen proyección `ALL` y los índices **no pueden leerse con consistencia fuerte**: las preguntas «¿tiene libros este autor?» o «¿tiene ejemplares esta sede?» pueden ir unos milisegundos detrás de la tabla en AWS.

### 4.3 Cómo se resuelve cada acceso

| Operación | Cómo |
| :--- | :--- |
| Detalle de un libro | `Query` `PK = BOOK#<isbn>` (lectura fuerte) |
| Login por email | `GetItem` del alias `USEREMAIL#<email>` → `GetItem` del usuario |
| Listar autores / géneros / sedes / usuarios | `Query` GSI1 por la lista correspondiente |
| Disponibilidad de un libro por sede | `Query` GSI2 `begins_with("available#")` + `BatchGet` de las sedes |
| Ejemplares de una sede, por estado | `Query` GSI3 `begins_with("COPY#<status>#")` |
| Reservas de un usuario / de una sede | `Query` GSI2 / GSI3 |
| Reservas abiertas, vencidas | `Query` GSI4 (`SK < ahora`) |
| Reserva abierta de un ejemplar | puntero `open_reservation_id` en el ejemplar |
| «¿Tiene libros este autor?» (el 409 al borrar) | `Query` GSI2 con `Limit = 1` — contar en DynamoDB es recorrer; preguntar si hay uno, no |
| **Listado del catálogo con filtros, búsqueda de texto, ciudades** | **OpenSearch** (4.5) |

### 4.4 Lo que el motor relacional daba gratis

*   **Ids autoincrementales**: un ítem `COUNTER#<entidad>` incrementado con `ADD seq :one`, atómico en el servidor. Las altas son operaciones de staff (raras) y las lecturas no tocan el contador. **El seed deja cada contador en el último id usado**; si no, el primer `POST` pisaría un registro sembrado.
*   **Unicidad** (`users.email`, `genres.name`): un ítem *alias* cuya PK es el valor único, escrito con `attribute_not_exists(PK)` en la misma transacción que la entidad. Borrar un usuario o cambiar su email mueve el alias en la misma transacción, así el email viejo no queda bloqueado.
*   **Transacciones**: las cinco transiciones que tocan ejemplar y reserva a la vez (`reservar`, `retirar`, `cancelar`, `devolver`, `marcar perdido`) más el vencimiento son un `TransactWriteItems` **condicionado**: no leen para después escribir, condicionan la escritura (`status = available`, «sigue abierta», `open_reservation_id = <esta reserva>`). Dos usuarios que reservan el mismo ejemplar a la vez: gana uno y el otro recibe un conflicto (409).
*   **Integridad referencial**: las claves foráneas desaparecen. Nada impide un `COPY#` que apunte a un `BOOK#` borrado salvo los chequeos de los services (`has_*`) y las condiciones de las transacciones. Depende de que esa lógica esté bien escrita.
*   **Migraciones**: no hay versionado de esquema. Cambiar la forma de un ítem es un backfill escrito a mano; `table.py` crea la tabla pero no versiona su evolución.

### 4.5 El índice de búsqueda (OpenSearch)

Los filtros de `GET /books` son combinables (`?genre_id=1&genre_id=2&city=Rosario&q=borges`); servirlos con copias exigiría un ítem por combinación. Por eso el catálogo se **proyecta** a un documento por libro (`_id` = ISBN):

```json
{
  "isbn": "9780307474728", "title": "Cien años de soledad", "title_sort": "Cien años de soledad",
  "language": "es", "pages": 417, "synopsis": "...", "cover_key": "covers/...",
  "authors": [{"id": 1, "name": "Gabriel García Márquez"}],
  "genres":  [{"id": 1, "name": "Ficción"}, {"id": 2, "name": "Novela"}],
  "available_cities": ["Buenos Aires", "Rosario"],
  "available_copies": 7
}
```

`available_cities` **dentro del documento del libro** es la decisión clave: «en Rosario» significa «con un ejemplar disponible hoy ahí», y con el campo adentro `genre_id=1&city=Rosario` es una sola query, no la intersección de dos motores.

*   **Solo lectura y descartable.** La API nunca escribe en el índice; lo alimenta únicamente el **indexador**, que lee el stream de la tabla (Lambda en AWS, un poller en local) y reconstruye el documento del libro afectado. `python -m app.reindex` lo rearma entero desde DynamoDB.
*   **Eventualmente consistente**: ~1 s entre una escritura y su aparición en el listado. El detalle de un libro y su disponibilidad no sufren esto (van a DynamoDB).
*   **Texto**: `multi_match` (nunca `query_string`, que interpretaría operadores del usuario) sobre título, autor, ISBN y sinopsis, sin tildes ni mayúsculas; se piden todas las palabras y la última puede estar a medias.
*   **Orden y paginación** por título (campo `title_sort`) con `from`/`size` y total exacto; los filtros son `terms` (OR dentro de un filtro, AND entre filtros).

### 4.6 Lo que se pierde, dicho claro

*   **Consultas ad-hoc.** No hay `psql` para preguntar algo que no se modeló: toda pregunta nueva necesita un GSI o un scan. Para analítica el camino es el ETL a Redshift/Athena, que deja de ser opcional.
*   **Joins y agregaciones sobre el modelo operativo.** Se resuelven desnormalizando (4.1) o en OpenSearch (4.5).
*   **Lecturas fuertes sobre los índices**, ver 4.2.
