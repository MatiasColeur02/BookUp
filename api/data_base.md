# Arquitectura de Base de Datos - BookUp

Este documento detalla el modelo de datos relacional para la plataforma BookUp, diseñado para ser desplegado sobre un motor relacional como PostgreSQL (concordante con la infraestructura en AWS RDS propuesta). 

Se parte del esquema conceptual inicial y se aplican principios de normalización para asegurar la integridad referencial, escalabilidad y un rendimiento óptimo en las búsquedas.

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

A continuación, se detalla la estructura final de las tablas para la base de datos relacional.

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
