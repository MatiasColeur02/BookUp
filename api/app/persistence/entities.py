"""Entidades del dominio, como dataclasses.

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


class CloseReason(str, enum.Enum):
    """Por qué se cerró una reserva. `cancelled_at`/`returned_at` dicen *cuándo*, pero no
    alcanzan: vencer y cancelar escriben los dos `cancelled_at`, y perder un ejemplar
    prestado escribe `returned_at` como una devolución."""

    cancelled = "cancelled"
    expired = "expired"
    returned = "returned"
    lost = "lost"


class CancelledBy(str, enum.Enum):
    """Quién canceló: el dueño de la reserva o el personal de la sede."""

    user = "user"
    library = "library"


class DeadlineKind(str, enum.Enum):
    """Qué plazo venció: el de retiro (sin retirar) o el de devolución (prestada)."""

    pickup = "pickup"
    return_ = "return"


# Valor de `Reservation.origin` en las reservas que escribe el seed.
SEED_ORIGIN = "seed"


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
    name: str
    role: UserRole
    # Solo en `AUTH_MODE=local`: con Cognito la contraseña la guarda Cognito, no la base.
    password_hash: str | None = None
    language: str = "es"
    # Solo para `librarian`: la sede que administra.
    library_id: int | None = None
    # El `sub` del User Pool de Cognito (`AUTH_MODE=cognito`). Se escribe junto con su alias
    # `USERSUB#<sub>`, así que no se cambia con `update` sino con `set_cognito_sub`.
    cognito_sub: str | None = None
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
    # Lo que pasó, para quien lea el historial (las notificaciones, `notifications-roadmap.md`
    # §5.1). Todos opcionales: una reserva escrita antes de que existieran sigue siendo válida.
    close_reason: CloseReason | None = None
    cancelled_by: CancelledBy | None = None
    picked_up_at: datetime | None = None
    # Marcas de «ya se avisó que venció el plazo». Las escribe el job de vencimientos con un
    # update condicional (`attribute_not_exists`): es lo que lo hace idempotente.
    pickup_deadline_notified_at: datetime | None = None
    return_deadline_notified_at: datetime | None = None
    # `SEED_ORIGIN` en las reservas sembradas: el notificador ignora sus `INSERT`.
    origin: str | None = None

    @property
    def is_open(self) -> bool:
        return self.cancelled_at is None and self.returned_at is None


class InboxKind(str, enum.Enum):
    """De quién es una bandeja: de un usuario, o compartida por el personal de una sede."""

    user = "user"
    library = "library"


@dataclass(frozen=True, kw_only=True)
class Notification:
    """Una notificación de una bandeja (`notifications-roadmap.md` §5.2).

    Es un mensaje histórico, no una vista: el título del libro y los nombres se copian al
    escribirla, y un renombre posterior no la cambia.
    """

    type: str
    title: str
    body: str
    reservation_id: int
    library_id: int
    isbn: str
    # El `occurred_at` del evento, no la hora de escritura: ordena la bandeja y es parte del id.
    created_at: datetime
    read_at: datetime | None = None
    # Quién la marcó como leída (en la bandeja de una sede, cuál de sus librarians).
    read_by: int | None = None
    # Desde cuándo DynamoDB la puede borrar (TTL). Lo calcula el service con la retención.
    delete_after: datetime | None = None
    # Id público y opaco, lo asigna el repository. El cliente no lo interpreta.
    id: str | None = None
