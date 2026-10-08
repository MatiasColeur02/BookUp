"""Forma de cada ítem de la tabla: entidad → atributos + claves.

Un solo lugar para "cómo se ve en la tabla una entidad", usado por los repositories (que lo
envuelven en una escritura condicional) **y por el seed** (que lo escribe en lotes). Sin
esto, el seed y los repositories tendrían dos copias del formato —incluidos los campos
desnormalizados— y el seed sembraría datos que la API no sabe leer.

Las funciones no conocen condiciones ni transacciones: solo devuelven el ítem.
"""

from __future__ import annotations

from typing import Any

from .. import keys
from ..entities import Author, Book, Genre, Library, PhysicalBook, Reservation, User
from . import _support as s

# Nombres de los contadores de ids (`COUNTER#<entidad>`). Los libros no tienen: su id es el
# ISBN. Los usa `next_id` en cada repository y el seed al dejar el contador en su valor.
COUNTERS = ("author", "genre", "library", "user", "physical_book", "reservation")


def author_item(author: Author) -> dict[str, Any]:
    return {**keys.author(author.id, author.name), **s.to_item(author)}


def genre_item(genre: Genre) -> dict[str, Any]:
    return {**keys.genre(genre.id, genre.name), **s.to_item(genre)}


def genre_alias_item(name: str, genre_id: int) -> dict[str, Any]:
    """Alias de unicidad del nombre: su PK *es* el valor único (ROADMAP §4.4)."""
    return {**keys.genre_name(name), "genre_id": genre_id}


def library_item(library: Library) -> dict[str, Any]:
    return {**keys.library(library.id, library.name), **s.to_item(library)}


def user_item(user: User) -> dict[str, Any]:
    return {**keys.user(user.id, user.name), **s.to_item(user)}


def user_alias_item(email: str, user_id: int) -> dict[str, Any]:
    """Alias de unicidad del email y lookup del login."""
    return {**keys.user_email(email), "user_id": user_id}


def book_item(book: Book) -> dict[str, Any]:
    """El ítem `META`. Autores y géneros van en ítems aparte (`*_link_item`)."""
    return {
        **keys.book(book.isbn, book.title),
        **s.to_item(book, exclude=("authors", "genres")),
    }


def author_link_item(isbn: str, author: Author) -> dict[str, Any]:
    return {**keys.book_author(isbn, author.id), "author_id": author.id, "author_name": author.name}


def genre_link_item(isbn: str, genre: Genre) -> dict[str, Any]:
    return {**keys.book_genre(isbn, genre.id), "genre_id": genre.id, "genre_name": genre.name}


def book_items(book: Book) -> list[dict[str, Any]]:
    return [
        book_item(book),
        *(author_link_item(book.isbn, a) for a in book.authors),
        *(genre_link_item(book.isbn, g) for g in book.genres),
    ]


def copy_item(copy: PhysicalBook) -> dict[str, Any]:
    return {**keys.copy(copy.id, copy.isbn, copy.library_id, copy.status.value), **s.to_item(copy)}


def reservation_item(reservation: Reservation) -> dict[str, Any]:
    """Una reserva abierta entra al índice disperso GSI4; una cerrada no."""
    return {
        **keys.reservation(
            reservation.id,
            reservation.user_id,
            reservation.library_id,
            reservation.reserved_at,
            open_until=reservation.expires_at if reservation.is_open else None,
        ),
        **s.to_item(reservation),
    }


def copy_reservation_item(copy_id: int, reservation_id: int) -> dict[str, Any]:
    return keys.copy_reservation(copy_id, reservation_id)
