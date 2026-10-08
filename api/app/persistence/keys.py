"""Formato de las claves de la tabla única `bookup`.

Este módulo es el **único lugar que conoce el formato** de `PK`/`SK` y de los cuatro
índices. Los repositories piden las claves de un ítem a una función de acá y nunca
arman un string `"BOOK#..."` a mano: el formato es el contrato interno de la tabla, y
repartido por siete archivos se desincroniza al primer cambio. Ver `ROADMAP.md` §3.

Las funciones son puras (sin boto3, sin I/O) y trabajan con tipos primitivos, no con
entidades: los enums llegan como su valor (`"available"`), los datetimes como datetime.

Dos criterios que atraviesan todo el archivo:

- **Los ids van con padding en las sort keys** (`0000000042`) y sin padding en las
  partition keys. Una SK se compara como string, y sin padding `"10"` ordena antes que
  `"9"`; una PK solo se compara por igualdad, así que `COPY#42` queda legible.
- **Los índices de listado ordenan por nombre plegado** (sin tildes ni mayúsculas): es
  lo que espera quien ordena una lista de nombres a mano (el orden de bytes de un string
  pone todas las mayúsculas antes que las minúsculas), y evita que "Álvaro" quede después de "Zapata".
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

# Atributos de clave de la tabla base y de cada índice (index overloading: los nombres
# son genéricos porque un mismo GSI sirve a varios tipos de ítem).
PK = "PK"
SK = "SK"

GSI1 = "GSI1"
GSI2 = "GSI2"
GSI3 = "GSI3"
GSI4 = "GSI4"
GSI1_PK, GSI1_SK = "GSI1PK", "GSI1SK"
GSI2_PK, GSI2_SK = "GSI2PK", "GSI2SK"
GSI3_PK, GSI3_SK = "GSI3PK", "GSI3SK"
GSI4_PK, GSI4_SK = "GSI4PK", "GSI4SK"

# Los dos atributos del índice disperso de reservas abiertas. Cerrar una reserva hace
# `REMOVE` de estos dos: un ítem sin ellos no existe en GSI4.
GSI4_ATTRIBUTES = (GSI4_PK, GSI4_SK)

META = "META"

# Valores de GSI1PK: una "lista" por tipo de entidad.
LIST_CATALOG = "CATALOG"
LIST_AUTHORS = "AUTHORS"
LIST_GENRES = "GENRES"
LIST_LIBRARIES = "LIBRARIES"
LIST_USERS = "USERS"
# Listados sin filtro de ejemplares y de reservas (`GET /physical-books`, `GET /reservations`
# de un sysadmin). Sin esto la única forma de listarlos enteros sería un Scan de la tabla.
LIST_COPIES = "COPIES"
LIST_RESERVATIONS = "RESERVATIONS"

# Valor fijo de GSI4PK: todas las reservas abiertas comparten partición del índice.
OPEN = "OPEN"

# Prefijos de SK para `begins_with` en el adjacency list de un libro.
AUTHOR_LINK_PREFIX = "AUTHOR#"
GENRE_LINK_PREFIX = "GENRE#"

# Ítem centinela que marca que el seed ya corrió (idempotencia).
SEED_PK = "SEED"


def pad(n: int) -> str:
    """Id como string de 10 dígitos, para que el orden lexicográfico sea el numérico."""
    return f"{n:010d}"


def fold(text: str) -> str:
    """Texto plegado para ordenar: sin tildes y sin distinguir mayúsculas."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def iso(moment: datetime) -> str:
    """Timestamp en UTC con ancho fijo, comparable como string.

    `isoformat()` no sirve para ordenar: omite los microsegundos cuando son cero y suma
    un offset distinto según la zona. Un datetime sin zona se toma como UTC.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _item(pk: str, sk: str, **index_attrs: str) -> dict[str, str]:
    return {PK: pk, SK: sk, **index_attrs}


def _listed(list_name: str, name: str, entity_id: int) -> dict[str, str]:
    return {GSI1_PK: list_name, GSI1_SK: f"{fold(name)}#{pad(entity_id)}"}


# ---------------------------------------------------------------------------
# Claves primarias sueltas, para GetItem / Query por partición.
# ---------------------------------------------------------------------------


def book_pk(isbn: str) -> str:
    return f"BOOK#{isbn}"


def author_pk(author_id: int) -> str:
    return f"AUTHOR#{author_id}"


def genre_pk(genre_id: int) -> str:
    return f"GENRE#{genre_id}"


def library_pk(library_id: int) -> str:
    return f"LIB#{library_id}"


def copy_pk(copy_id: int) -> str:
    return f"COPY#{copy_id}"


def reservation_pk(reservation_id: int) -> str:
    return f"RES#{reservation_id}"


def user_pk(user_id: int) -> str:
    return f"USER#{user_id}"


def key(pk: str, sk: str = META) -> dict[str, str]:
    """Clave primaria completa, lista para `Key=` de GetItem/UpdateItem/DeleteItem."""
    return {PK: pk, SK: sk}


# ---------------------------------------------------------------------------
# Ítems por entidad: clave primaria + atributos de índice.
# ---------------------------------------------------------------------------


def book(isbn: str, title: str) -> dict[str, str]:
    # El desempate es el isbn (la PK del libro), no un id numérico.
    return _item(
        book_pk(isbn),
        META,
        **{GSI1_PK: LIST_CATALOG, GSI1_SK: f"{fold(title)}#{isbn}"},
    )


def book_author(isbn: str, author_id: int) -> dict[str, str]:
    """Enlace libro↔autor. GSI2 lo da vuelta: los libros de un autor."""
    return _item(
        book_pk(isbn),
        f"{AUTHOR_LINK_PREFIX}{author_id}",
        **{GSI2_PK: author_pk(author_id), GSI2_SK: book_pk(isbn)},
    )


def book_genre(isbn: str, genre_id: int) -> dict[str, str]:
    """Enlace libro↔género. GSI2 lo da vuelta: los libros de un género."""
    return _item(
        book_pk(isbn),
        f"{GENRE_LINK_PREFIX}{genre_id}",
        **{GSI2_PK: genre_pk(genre_id), GSI2_SK: book_pk(isbn)},
    )


def author(author_id: int, name: str) -> dict[str, str]:
    return _item(author_pk(author_id), META, **_listed(LIST_AUTHORS, name, author_id))


def genre(genre_id: int, name: str) -> dict[str, str]:
    return _item(genre_pk(genre_id), META, **_listed(LIST_GENRES, name, genre_id))


def library(library_id: int, name: str) -> dict[str, str]:
    return _item(library_pk(library_id), META, **_listed(LIST_LIBRARIES, name, library_id))


def user(user_id: int, name: str) -> dict[str, str]:
    return _item(user_pk(user_id), META, **_listed(LIST_USERS, name, user_id))


def copy(copy_id: int, isbn: str, library_id: int, status: str) -> dict[str, str]:
    """Ejemplar. Cambiar `status` obliga a reescribir `GSI2SK` y `GSI3SK`.

    - GSI1: la lista de todos los ejemplares, por id.
    - GSI2: PK = el libro, SK = `<status>#LIB#<sede>#<id>` → los disponibles de un libro
      salen agrupados por sede con un `begins_with(SK, "available#")`.
    - GSI3: PK = la sede, SK = `COPY#<status>#<isbn>#<id>` → los ejemplares de una sede,
      opcionalmente de un estado.
    """
    return _item(
        copy_pk(copy_id),
        META,
        **{
            GSI1_PK: LIST_COPIES,
            GSI1_SK: pad(copy_id),
            GSI2_PK: book_pk(isbn),
            GSI2_SK: f"{status}#LIB#{pad(library_id)}#{pad(copy_id)}",
            GSI3_PK: library_pk(library_id),
            GSI3_SK: f"COPY#{status}#{isbn}#{pad(copy_id)}",
        },
    )


def reservation(
    reservation_id: int,
    user_id: int,
    library_id: int,
    reserved_at: datetime,
    *,
    open_until: datetime | None = None,
) -> dict[str, str]:
    """Reserva. `open_until` (su `expires_at`) la mete en el índice disperso GSI4.

    Para una reserva ya cerrada hay que pasarlo en `None`: el ítem no lleva `GSI4*` y
    por eso no existe en el índice. Al cerrar una existente, además de reescribir el
    ítem, la expresión de update hace `REMOVE` de `GSI4_ATTRIBUTES`.

    GSI1 es la lista de todas, por id; GSI2 agrupa por usuario
    (`list_all(user_id=...)`); GSI3 por sede.
    """
    sort = f"RES#{iso(reserved_at)}#{pad(reservation_id)}"
    attrs = {
        GSI1_PK: LIST_RESERVATIONS,
        GSI1_SK: pad(reservation_id),
        GSI2_PK: user_pk(user_id),
        GSI2_SK: sort,
        GSI3_PK: library_pk(library_id),
        GSI3_SK: sort,
    }
    if open_until is not None:
        attrs.update(open_reservation_index(reservation_id, open_until))
    return _item(reservation_pk(reservation_id), META, **attrs)


def open_reservation_index(reservation_id: int, expires_at: datetime) -> dict[str, str]:
    """Los dos atributos de GSI4, por separado de `reservation()` para poder armar un
    `SET` o un `REMOVE` sobre ellos sin reconstruir el resto de las claves."""
    return {GSI4_PK: OPEN, GSI4_SK: f"{iso(expires_at)}#{pad(reservation_id)}"}


def copy_reservation(copy_id: int, reservation_id: int) -> dict[str, str]:
    """Ítem de enlace ejemplar→reserva, en la partición del ejemplar.

    GSI2 de la reserva ya está tomado por el usuario (un ítem tiene un solo `GSI2PK`),
    así que "¿este ejemplar tuvo alguna reserva?" —el 409 de `DELETE /physical-books`—
    se resuelve con un `Query` de la partición `COPY#<id>` con `begins_with(SK, "RES#")`
    y `Limit=1`, lectura fuerte. Se escribe en la misma transacción que la reserva.
    """
    return _item(copy_pk(copy_id), reservation_pk(reservation_id))


# ---------------------------------------------------------------------------
# Ítems de soporte: unicidad, contadores, seed.
# ---------------------------------------------------------------------------


def user_email(email: str) -> dict[str, str]:
    """Alias de unicidad y lookup del login. El email se usa tal cual, como hoy."""
    return _item(f"USEREMAIL#{email}", META)


def genre_name(name: str) -> dict[str, str]:
    """Alias de unicidad del nombre de un género."""
    return _item(f"GENRENAME#{name}", META)


def counter(entity: str) -> dict[str, str]:
    """Contador de ids de una entidad (`author`, `book`, ...)."""
    return key(f"COUNTER#{entity}")


def seed_marker() -> dict[str, str]:
    return key(SEED_PK)


# ---------------------------------------------------------------------------
# Prefijos y cotas para los `KeyConditionExpression`.
# ---------------------------------------------------------------------------


def copy_status_prefix(status: str) -> str:
    """Prefijo de `GSI2SK` de los ejemplares de un libro en un estado."""
    return f"{status}#"


def library_copies_prefix(status: str | None = None) -> str:
    """Prefijo de `GSI3SK` de los ejemplares de una sede, opcionalmente de un estado."""
    return f"COPY#{status}#" if status else "COPY#"


def library_reservations_prefix() -> str:
    """Prefijo de `GSI3SK` de las reservas de una sede."""
    return "RES#"


def user_reservations_prefix() -> str:
    """Prefijo de `GSI2SK` de las reservas de un usuario."""
    return "RES#"


def copy_reservations_prefix() -> str:
    """Prefijo de `SK` de los enlaces ejemplar→reserva de `copy_reservation`."""
    return "RES#"


def expires_before(now: datetime) -> str:
    """Cota para `GSI4SK < :bound`: las reservas abiertas cuyo `expires_at` ya pasó.

    Es estricta a propósito, igual que el `expires_at < now` de hoy: el timestamp solo
    es prefijo de cualquier `GSI4SK` con ese mismo instante, así que ordena antes y ese
    ítem queda afuera.
    """
    return iso(now)
