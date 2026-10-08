from __future__ import annotations

import dataclasses

from ..dynamo import Dynamo
from ..entities import Library, PhysicalBook, PhysicalBookStatus
from ..errors import ConditionFailedError
from .. import keys
from . import _support as s
from .library_repository import LibraryRepository
from .reservation_repository import ReservationRepository

_NEW = "attribute_not_exists(PK)"
_STATUS = {"#st": "status"}


def status_keys(copy_id: int, isbn: str, library_id: int, status: PhysicalBookStatus | str):
    """`GSI2SK` y `GSI3SK` de un ejemplar en un estado: lo que hay que reescribir en cada
    cambio de `status`, porque ambos índices llevan el estado dentro de la sort key."""
    value = status.value if isinstance(status, PhysicalBookStatus) else status
    item = keys.copy(copy_id, isbn, library_id, value)
    return {keys.GSI2_SK: item[keys.GSI2_SK], keys.GSI3_SK: item[keys.GSI3_SK]}


class PhysicalBookRepository:
    def __init__(self, db: Dynamo):
        self.db = db

    @staticmethod
    def _entity(item: dict) -> PhysicalBook:
        return s.from_item(PhysicalBook, item)

    def get(self, physical_book_id: int) -> PhysicalBook | None:
        item = s.get_item(self.db, keys.copy_pk(physical_book_id))
        return self._entity(item) if item else None

    def list_all(
        self,
        isbn: str | None = None,
        library_id: int | None = None,
        status: PhysicalBookStatus | None = None,
    ) -> list[PhysicalBook]:
        """Ejemplares, por id. Elige el índice según el filtro más selectivo que traiga:
        la sede (GSI3), si no el libro (GSI2), si no la lista completa (GSI1). Lo que el
        índice no resuelve se filtra del lado del servidor."""
        names: dict[str, str] = {}
        values: dict[str, object] = {}
        filters: list[str] = []

        if library_id is not None:
            index = keys.GSI3
            condition = "GSI3PK = :pk AND begins_with(GSI3SK, :prefix)"
            values[":pk"] = keys.library_pk(library_id)
            values[":prefix"] = keys.library_copies_prefix(status.value if status else None)
            if isbn is not None:
                filters.append("isbn = :isbn")
                values[":isbn"] = isbn
        elif isbn is not None:
            index = keys.GSI2
            values[":pk"] = keys.book_pk(isbn)
            if status is not None:
                condition = "GSI2PK = :pk AND begins_with(GSI2SK, :prefix)"
                values[":prefix"] = keys.copy_status_prefix(status.value)
            else:
                condition = "GSI2PK = :pk"
        else:
            index = keys.GSI1
            condition = "GSI1PK = :pk"
            values[":pk"] = keys.LIST_COPIES
            if status is not None:
                names.update(_STATUS)
                filters.append("#st = :status")
                values[":status"] = status.value

        kwargs: dict = {
            "IndexName": index,
            "KeyConditionExpression": condition,
            "ExpressionAttributeValues": values,
        }
        if names:
            kwargs["ExpressionAttributeNames"] = names
        if filters:
            kwargs["FilterExpression"] = " AND ".join(filters)
        items = s.query_all(self.db, **kwargs)
        return sorted((self._entity(i) for i in items), key=lambda c: c.id)

    def create(self, physical_book: PhysicalBook) -> PhysicalBook:
        """Alta de un ejemplar, copiándole el título, el nombre y la ciudad de la sede.

        Los `ConditionCheck` cierran la ventana entre leer el libro y la sede y escribir
        el ejemplar: si alguno se borró en el medio, no queda un ejemplar huérfano.
        """
        book = s.get_item(self.db, keys.book_pk(physical_book.isbn))
        library = LibraryRepository(self.db).get(physical_book.library_id)
        if book is None:
            raise ConditionFailedError(f"Book {physical_book.isbn} does not exist")
        if library is None:
            raise ConditionFailedError(f"Library {physical_book.library_id} does not exist")

        created = dataclasses.replace(
            physical_book,
            id=s.next_id(self.db, "physical_book"),
            open_reservation_id=None,
            library_name=library.name,
            library_city=library.city,
            book_title=book["title"],
        )
        item = {
            **keys.copy(created.id, created.isbn, created.library_id, created.status.value),
            **s.to_item(created),
        }
        s.run_transaction(
            self.db,
            [
                s.tx_check(keys.key(keys.book_pk(created.isbn)), "attribute_exists(PK)"),
                s.tx_check(keys.key(keys.library_pk(created.library_id)), "attribute_exists(PK)"),
                s.tx_put(item, condition=_NEW),
            ],
            failed_error="The book or the library was deleted while the copy was being created",
        )
        return created

    def update_status(
        self, physical_book_id: int, status: PhysicalBookStatus
    ) -> PhysicalBook:
        """Pasa un ejemplar a `lost` o lo devuelve a `available` (los destinos manuales).

        - `lost` siempre se puede. Si el ejemplar tenía una reserva abierta, se cierra en
          la **misma transacción** (prestada → devuelta, pendiente → cancelada).
        - `available` solo sale de `lost`: liberar un ejemplar retenido es tarea de
          cancel/return, y la condición lo garantiza aunque un request llegue en el medio.
        """
        if status is PhysicalBookStatus.available:
            return self._set_status(
                physical_book_id,
                status,
                "(#st = :lost OR #st = :available)",
                {":lost": "lost", ":available": "available"},
            )
        if status is not PhysicalBookStatus.lost:
            raise ValueError(f"{status.value} is driven by the reservation flow")

        # Si la reserva abierta cambia entre leer el ejemplar y escribir, se relee.
        for _ in range(3):
            copy = self.get(physical_book_id)
            if copy is None:
                raise ConditionFailedError(f"Physical book {physical_book_id} does not exist")
            try:
                if copy.open_reservation_id is None:
                    return self._set_status(
                        physical_book_id,
                        status,
                        "attribute_not_exists(open_reservation_id)",
                        {},
                    )
                ReservationRepository(self.db).release_lost_copy(copy.open_reservation_id)
                return self.get(physical_book_id)
            except ConditionFailedError:
                continue
        raise ConditionFailedError(
            f"Physical book {physical_book_id} kept changing while it was marked lost"
        )

    def _set_status(
        self, physical_book_id: int, status: PhysicalBookStatus, condition: str, values: dict
    ) -> PhysicalBook:
        copy = self.get(physical_book_id)
        if copy is None:
            raise ConditionFailedError(f"Physical book {physical_book_id} does not exist")
        s.run_transaction(
            self.db,
            [
                s.tx_update(
                    keys.key(keys.copy_pk(physical_book_id)),
                    set_={
                        "status": status,
                        **status_keys(physical_book_id, copy.isbn, copy.library_id, status),
                    },
                    condition=f"attribute_exists(PK) AND {condition}",
                    # DynamoDB rechaza un alias que la expresión no usa.
                    names=_STATUS if "#st" in condition else None,
                    values=values,
                )
            ],
            failed_error=f"Physical book {physical_book_id} is {copy.status.value}",
        )
        return dataclasses.replace(copy, status=status)

    def delete(self, physical_book: PhysicalBook) -> None:
        self.db.table.delete_item(Key=keys.key(keys.copy_pk(physical_book.id)))

    def has_reservations(self, physical_book_id: int) -> bool:
        """¿Alguna vez tuvo una reserva (abierta o cerrada)? Es el 409 del `DELETE`.

        Se resuelve con el ítem de enlace `COPY#<id>/RES#<id>` (ver `keys.copy_reservation`)
        y no con un índice, y como es la tabla base la lectura es fuerte.
        """
        return s.exists_any(
            self.db,
            ConsistentRead=True,
            KeyConditionExpression="PK = :pk AND begins_with(SK, :res)",
            ExpressionAttributeValues={
                ":pk": keys.copy_pk(physical_book_id),
                ":res": keys.copy_reservations_prefix(),
            },
        )

    def available_by_book(self, isbn: str) -> list[tuple[Library, list[PhysicalBook]]]:
        """Ejemplares disponibles de un libro agrupados por sede.

        Un Query a GSI2 con `begins_with("available#")` devuelve solo los disponibles, ya
        agrupados por sede y ordenados; la sede (dirección, horarios) se trae con un
        BatchGet. Dos round-trips en total, sin leer prestados ni perdidos.
        """
        items = s.query_all(
            self.db,
            IndexName=keys.GSI2,
            KeyConditionExpression="GSI2PK = :book AND begins_with(GSI2SK, :available)",
            ExpressionAttributeValues={
                ":book": keys.book_pk(isbn),
                ":available": keys.copy_status_prefix(PhysicalBookStatus.available.value),
            },
        )
        by_library: dict[int, list[PhysicalBook]] = {}
        for item in items:
            copy = self._entity(item)
            by_library.setdefault(copy.library_id, []).append(copy)

        libraries = {lib.id: lib for lib in LibraryRepository(self.db).get_many(list(by_library))}
        return [
            (libraries[library_id], copies)
            for library_id, copies in by_library.items()
            if library_id in libraries
        ]
