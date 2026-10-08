from datetime import datetime, timedelta, timezone
from typing import Any, Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from .. import storage
from ..persistence.entities import PhysicalBookStatus, UserRole


def _text(max_length: int, *, min_length: int = 1) -> Any:
    """Texto acotado, sin espacios de sobra en las puntas.

    Los topes replican el ancho de la columna correspondiente en `models.py`. No es
    cosmético: sin ellos un texto más largo que la columna pasa la validación, revienta
    recién en Postgres (`StringDataRightTruncation`) y el cliente recibe un 500 en lugar
    del 422 que corresponde. SQLite, que es lo que usa la suite, ignora el ancho de un
    VARCHAR, así que este límite es la única defensa que corre en los tests.

    `min_length=0` se usa en los opcionales: el frontend manda "" para vaciar un campo.
    """
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
    ]


# Techo de una reserva. Sin esto `expires_at` solo tiene que ser futuro, y un
# `expires_at` en el año 9999 retiene un ejemplar para siempre.
MAX_RESERVATION_DAYS = 365

# bcrypt solo mira los primeros 72 bytes de la contraseña y descarta el resto **sin
# avisar**: sin este tope, dos contraseñas que comparten los primeros 72 bytes son la
# misma para el login. Se rechaza explícitamente en vez de truncar en silencio.
MAX_PASSWORD_BYTES = 72


def _validate_future(value: datetime) -> datetime:
    """A reservation that expires in the past would be born already expired."""
    # A naive datetime is read as UTC, the timezone every stored date uses.
    reference = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if reference <= now:
        raise ValueError("expires_at must be in the future")
    if reference > now + timedelta(days=MAX_RESERVATION_DAYS):
        raise ValueError(f"expires_at cannot be more than {MAX_RESERVATION_DAYS} days away")
    return value


def _validate_password(value: str) -> str:
    """Rechaza lo que bcrypt truncaría en silencio (ver `MAX_PASSWORD_BYTES`)."""
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password cannot be longer than {MAX_PASSWORD_BYTES} bytes")
    return value


def _validate_email_length(value: str) -> str:
    """`User.email` es un String(255): más largo que eso no entra en la columna."""
    if len(value) > 255:
        raise ValueError("email cannot be longer than 255 characters")
    return value


def _validate_isbn13(isbn: str) -> str:
    """`Book.isbn` is a String(13) primary key, so only well-formed ISBN-13 gets in."""
    if len(isbn) != 13 or not isbn.isdigit():
        raise ValueError("isbn must be 13 digits")
    # Check digit: digits weighted 1,3,1,3,... must add up to a multiple of 10.
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(isbn))
    if total % 10 != 0:
        raise ValueError("isbn has an invalid check digit")
    return isbn


class LibraryBase(BaseModel):
    name: _text(150)
    address: _text(255)
    state: _text(100)
    city: _text(100)
    # Los opcionales admiten "": es como el frontend vacía un campo ya cargado.
    hours: _text(255, min_length=0) | None = None
    phone: _text(50, min_length=0) | None = None
    email: _text(255, min_length=0) | None = None
    website: _text(255, min_length=0) | None = None


class LibraryCreate(LibraryBase):
    pass


class LibraryUpdate(BaseModel):
    name: _text(150) | None = None
    address: _text(255) | None = None
    state: _text(100) | None = None
    city: _text(100) | None = None
    hours: _text(255, min_length=0) | None = None
    phone: _text(50, min_length=0) | None = None
    email: _text(255, min_length=0) | None = None
    website: _text(255, min_length=0) | None = None


class LibraryOut(LibraryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class GenreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class BookBase(BaseModel):
    isbn: _text(13)
    title: _text(255)
    language: _text(50)
    # `pages` no tiene columna que lo acote (es un Integer), así que el rango lo pone
    # el dominio: 0 o negativo no es un libro, y 50.000 páginas tampoco.
    pages: int | None = Field(default=None, ge=1, le=50_000)
    # `synopsis` es un Text: la base no tiene tope, así que sin este límite un POST
    # puede escribir megabytes por fila.
    synopsis: _text(5_000, min_length=0) | None = None


class BookOut(BookBase):
    model_config = ConfigDict(from_attributes=True)
    authors: list[AuthorOut] = []
    genres: list[GenreOut] = []
    # URL de lectura de la portada, derivada de `Book.cover_key` (la key nunca se
    # expone). Es un campo normal y no un `computed_field` porque el payload viaja por
    # el cache: al revalidar el JSON cacheado no hay `cover_key` del que recalcularla.
    cover_url: str | None = None

    @classmethod
    def from_book(cls, book) -> "BookOut":
        """Construye el esquema resolviendo la portada.

        Todo endpoint que devuelva libros tiene que pasar por acá: validar la entidad
        ORM directamente deja `cover_url` en `None`.
        """
        out = cls.model_validate(book)
        out.cover_url = storage.public_url(book.cover_key)
        return out


class BookPage(BaseModel):
    """Página del catálogo. `total` es el catálogo entero, no la página."""

    items: list[BookOut]
    total: int
    limit: int
    offset: int


class BookCreate(BookBase):
    author_ids: list[int] = []
    genre_ids: list[int] = []

    @field_validator("isbn")
    @classmethod
    def check_isbn(cls, value: str) -> str:
        return _validate_isbn13(value)


class CoverUploadRequest(BaseModel):
    """Pedido de URL firmada para subir una portada."""

    # El valor se compara contra `storage.ALLOWED_CONTENT_TYPES` en el controller; acá
    # solo se acota el largo para no arrastrar un string arbitrario.
    content_type: _text(100)
    # `size` es lo que **declara** el cliente y por eso no alcanza: el tamaño real se
    # verifica contra el objeto ya subido al confirmar la key. Ver `attach_cover`.
    size: int = Field(gt=0)


class CoverUploadOut(BaseModel):
    """Lo que el browser necesita para el `PUT` directo a S3 y la confirmación posterior."""

    upload_url: str
    key: str
    # El `PUT` tiene que mandar exactamente este content-type: va firmado en la URL.
    content_type: str
    expires_in: int


class CoverAttach(BaseModel):
    """Confirmación: la key que el browser terminó de subir."""

    # `Book.cover_key` es un String(255). Que la key sea de este libro lo valida
    # `storage.owns_key` en el controller.
    key: _text(255)


class BookUpdate(BaseModel):
    title: _text(255) | None = None
    language: _text(50) | None = None
    pages: int | None = Field(default=None, ge=1, le=50_000)
    synopsis: _text(5_000, min_length=0) | None = None
    # Sending a list replaces the whole association; omitting it leaves it as is.
    author_ids: list[int] | None = None
    genre_ids: list[int] | None = None


class AuthorCreate(BaseModel):
    name: _text(200)


class AuthorUpdate(BaseModel):
    name: _text(200) | None = None


class GenreCreate(BaseModel):
    name: _text(100)


class GenreUpdate(BaseModel):
    name: _text(100) | None = None


class PhysicalBookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    isbn: str
    library_id: int
    status: PhysicalBookStatus


class PhysicalBookCreate(BaseModel):
    isbn: _text(13)
    library_id: int

    @field_validator("isbn")
    @classmethod
    def check_isbn(cls, value: str) -> str:
        return _validate_isbn13(value)


class PhysicalBookStatusUpdate(BaseModel):
    status: PhysicalBookStatus


class LibraryAvailability(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    library: LibraryOut
    available_copies: int
    # A representative physical book id from this library, ready to be reserved.
    physical_book_id: int


class BookAvailability(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    book: BookOut
    libraries: list[LibraryAvailability]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    language: str
    role: UserRole
    library_id: int | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)
    name: _text(150)
    language: _text(10) = "es"

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return _validate_email_length(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return _validate_password(value)


class UserStaffCreate(BaseModel):
    """Alta de personal (`librarian`/`sysadmin`); solo para sysadmins."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)
    name: _text(150)
    language: _text(10) = "es"
    role: UserRole
    library_id: int | None = None

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return _validate_email_length(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return _validate_password(value)


class UserUpdate(BaseModel):
    name: _text(150) | None = None
    language: _text(10) | None = None
    password: str | None = Field(default=None, min_length=8, max_length=MAX_PASSWORD_BYTES)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str | None) -> str | None:
        return None if value is None else _validate_password(value)
    # Only a sysadmin may send these two; anyone else gets a 403.
    role: UserRole | None = None
    library_id: int | None = None


class LoginRequest(BaseModel):
    # Acotados por la misma razón que en el alta: son la entrada de un endpoint público
    # y sin sesión, así que es la superficie más expuesta de la API.
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return _validate_email_length(value)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ReservationCreate(BaseModel):
    physical_book_id: int
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def check_future(cls, value: datetime) -> datetime:
        return _validate_future(value)


class ReservationUpdate(BaseModel):
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def check_future(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_future(value)


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    physical_book_id: int
    reserved_at: datetime
    expires_at: datetime
    picked_up: bool
    cancelled_at: datetime | None = None
    returned_at: datetime | None = None


class ExpiredReservations(BaseModel):
    expired: int
