"""Repositories sobre DynamoDB: la reescritura de `persistence/repositories/`.

Conviven con los de SQLAlchemy hasta la fase 4, cuando los services pasan a usar estos y
el paquete viejo se borra (fase 7). Misma interfaz pública que los originales salvo tres
cambios que pide el roadmap: los `count_*` pasan a `has_*` (§4.5), `update(...)` reemplaza
a la mutación en el lugar de la entidad (§7.2), y las transiciones de reserva viven en
`ReservationRepository` (§4.2).
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
