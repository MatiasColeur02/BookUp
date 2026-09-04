from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from ..persistence.models import ReservationStatus


class LibraryBase(BaseModel):
    name: str
    city: str
    address: str | None = None


class LibraryCreate(LibraryBase):
    pass


class LibraryOut(LibraryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BookBase(BaseModel):
    title: str
    author: str
    isbn: str
    synopsis: str | None = None


class BookOut(BookBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LibraryAvailability(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    library: LibraryOut
    available_copies: int
    # A representative copy id from this library, ready to be reserved.
    copy_id: int


class BookAvailability(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    book: BookOut
    libraries: list[LibraryAvailability]


class ReservationCreate(BaseModel):
    copy_id: int
    patron_name: str
    patron_email: EmailStr


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    copy_id: int
    patron_name: str
    patron_email: str
    status: ReservationStatus
    created_at: datetime
    confirmed_by: str | None = None
