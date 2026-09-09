from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .. import storage
from ..persistence.models import PhysicalBookStatus, UserRole


def _validate_future(value: datetime) -> datetime:
    """A reservation that expires in the past would be born already expired."""
    # A naive datetime is read as UTC, the timezone every stored date uses.
    reference = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if reference <= datetime.now(timezone.utc):
        raise ValueError("expires_at must be in the future")
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
    name: str
    address: str
    state: str
    city: str
    hours: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None


class LibraryCreate(LibraryBase):
    pass


class LibraryUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    state: str | None = None
    city: str | None = None
    hours: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None


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
    isbn: str
    title: str
    language: str
    pages: int | None = None
    synopsis: str | None = None


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

    content_type: str
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

    key: str


class BookUpdate(BaseModel):
    title: str | None = None
    language: str | None = None
    pages: int | None = None
    synopsis: str | None = None
    # Sending a list replaces the whole association; omitting it leaves it as is.
    author_ids: list[int] | None = None
    genre_ids: list[int] | None = None


class AuthorCreate(BaseModel):
    name: str = Field(min_length=1)


class AuthorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)


class GenreCreate(BaseModel):
    name: str = Field(min_length=1)


class GenreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)


class PhysicalBookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    isbn: str
    library_id: int
    status: PhysicalBookStatus


class PhysicalBookCreate(BaseModel):
    isbn: str
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
    password: str = Field(min_length=8)
    name: str
    language: str = "es"


class UserStaffCreate(BaseModel):
    """Alta de personal (`librarian`/`sysadmin`); solo para sysadmins."""

    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    language: str = "es"
    role: UserRole
    library_id: int | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    language: str | None = None
    password: str | None = Field(default=None, min_length=8)
    # Only a sysadmin may send these two; anyone else gets a 403.
    role: UserRole | None = None
    library_id: int | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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
