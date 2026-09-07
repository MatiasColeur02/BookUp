from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..persistence.models import UserRole


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


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    physical_book_id: int
    reserved_at: datetime
    expires_at: datetime
    picked_up: bool
