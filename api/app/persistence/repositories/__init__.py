"""Repositories sobre DynamoDB: un acceso a datos por entidad, único lugar que conoce el motor.

Los services reciben un `Dynamo` y arman `XRepository(db)`; no ven boto3, claves ni
transacciones. Tres convenciones: las preguntas del tipo «¿hay al menos uno?» son `has_*`
(contar en DynamoDB es recorrer), un cambio es `update(id, **cambios)` y devuelve la entidad
nueva (las entidades son inmutables), y las transiciones de reserva —que escriben la reserva
y su ejemplar juntos— viven en `ReservationRepository`. El formato de los ítems está en
`_items.py` y el de las claves en `persistence/keys.py`.
"""

from .author_repository import AuthorRepository
from .book_repository import BookRepository
from .genre_repository import GenreRepository
from .library_repository import LibraryRepository
from .physical_book_repository import PhysicalBookRepository
from .reservation_repository import ReservationRepository
from .user_repository import UserRepository

__all__ = [
    "AuthorRepository",
    "BookRepository",
    "GenreRepository",
    "LibraryRepository",
    "PhysicalBookRepository",
    "ReservationRepository",
    "UserRepository",
]
