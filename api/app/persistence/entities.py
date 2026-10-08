"""Entidades del dominio como dataclasses: el reemplazo de las clases ORM de `models.py`.

No hay mapeo, sesión ni relaciones lazy: una entidad es un valor inmutable que un
repository arma al leer de DynamoDB y que un service recibe y devuelve. Para "cambiarla"
se pide al repository que la actualice (`repo.update(id, name=...)`) y devuelve una nueva;
`frozen=True` hace que olvidarse de eso sea un error en el acto y no una escritura que
nunca ocurre. Ver `ROADMAP.md` §7.1.

Tres convenciones:

- **`kw_only`**: los services construyen las entidades con argumentos con nombre, y así
  los campos con default no obligan a ordenar los obligatorios primero.
- **Lo que asigna la persistencia arranca en `None`**: `id` (lo da el contador), y
  `reserved_at` y los timestamps. El repository devuelve la entidad ya completa.
- **Los campos desnormalizados no son parte del dominio**: `library_city`, `book_title`,
  `Reservation.library_id`, etc. los mantiene el repository para no tener que navegar
  relaciones (`reservation.physical_book.library_id`). Un service puede leerlos, pero no
  los arma; ver `ROADMAP.md` §3.1.

`UserRole` y `PhysicalBookStatus` viven acá y `models.py` los importa, así que durante la
migración hay una sola definición de cada enum.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class UserRole(str, enum.Enum):
    customer = "customer"
    librarian = "librarian"
    sysadmin = "sysadmin"


class PhysicalBookStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"
    loaned = "loaned"
    lost = "lost"


@dataclass(frozen=True, kw_only=True)
class Author:
    name: str
    id: int | None = None


@dataclass(frozen=True, kw_only=True)
class Genre:
    name: str
    id: int | None = None


@dataclass(frozen=True, kw_only=True)
class Library:
    """Una sede."""

    name: str
    address: str
    state: str
    city: str
    hours: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    id: int | None = None


@dataclass(frozen=True, kw_only=True)
class Book:
    """Metadatos de catálogo de un libro, identificado por su ISBN."""

    isbn: str
    title: str
    language: str
    pages: int | None = None
    synopsis: str | None = None
    # Key del objeto en S3, no la URL (ver `app/storage.py`).
    cover_key: str | None = None
    # Vienen de los ítems `BOOK#<isbn>/AUTHOR#<id>` y `/GENRE#<id>`, que llevan el nombre
    # desnormalizado: el libro y sus autores y géneros salen de un solo Query.
    authors: list[Author] = field(default_factory=list)
    genres: list[Genre] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class PhysicalBook:
    """Un ejemplar (copia física) de un libro, en una sede."""

    isbn: str
    library_id: int
    status: PhysicalBookStatus = PhysicalBookStatus.available
    id: int | None = None
    # La reserva abierta del ejemplar, si la hay. Un ejemplar tiene a lo sumo una.
    open_reservation_id: int | None = None
    # Desnormalizados (los mantiene el repository): evitan un join a `Library` y a `Book`
    # al listar disponibilidad y ciudades.
    library_name: str | None = None
    library_city: str | None = None
    book_title: str | None = None


@dataclass(frozen=True, kw_only=True)
class User:
    """Un usuario de la plataforma: lector (customer) o personal de una sede."""

    email: str
    password_hash: str
    name: str
    role: UserRole
    language: str = "es"
    # Solo para `librarian`: la sede que administra.
    library_id: int | None = None
    id: int | None = None


@dataclass(frozen=True, kw_only=True)
class Reservation:
    """La reserva de un ejemplar por un usuario.

    Sin enum de estados: está **abierta** mientras `cancelled_at` y `returned_at` sean
    `None`, y `picked_up` distingue "reservada" de "prestada". Cerrarla libera el
    ejemplar. Nunca se borra el ítem, para conservar el historial de préstamos.
    """

    user_id: int
    physical_book_id: int
    expires_at: datetime
    picked_up: bool = False
    cancelled_at: datetime | None = None
    returned_at: datetime | None = None
    id: int | None = None
    reserved_at: datetime | None = None
    # Desnormalizados del ejemplar al reservar: con `library_id` la autorización de un
    # librarian no necesita cargar el ejemplar, y GSI3 lista por sede.
    library_id: int | None = None
    isbn: str | None = None

    @property
    def is_open(self) -> bool:
        return self.cancelled_at is None and self.returned_at is None
