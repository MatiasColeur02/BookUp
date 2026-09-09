from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import Author, Book, Library, PhysicalBook, PhysicalBookStatus, book_authors, book_genres


class BookRepository:
    """Data access for the book catalog.

    ``search`` uses a plain ILIKE scan for the MVP; in the target AWS
    architecture this query is replaced by a call to a managed search
    engine (OpenSearch) kept in sync with this table.
    """

    def __init__(self, db: Session):
        self.db = db

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Book]:
        stmt = select(Book).order_by(Book.title).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def count_all(self) -> int:
        return self.db.scalar(select(func.count()).select_from(Book))

    def _filters(
        self,
        *,
        query: str | None,
        author_ids: list[int],
        genre_ids: list[int],
        cities: list[str],
    ) -> list:
        """Condiciones de `list_filtered`, todas como EXISTS.

        Con EXISTS y no con JOIN a propósito: un libro con tres autores haría tres filas
        y habría que andar deduplicando la página y el `COUNT`. Un EXISTS deja una fila
        por libro y el conteo sale directo.

        Dentro de un filtro los valores suman (OR: "novela **o** cuento"); entre filtros
        se acumulan (AND: "novela, **y** en Rosario"). Es lo que espera cualquiera que
        haya usado filtros de una tienda.
        """
        conditions = []

        if query:
            pattern = f"%{query}%"
            author_match = (
                select(1)
                .select_from(book_authors.join(Author, Author.id == book_authors.c.author_id))
                .where(book_authors.c.isbn == Book.isbn, Author.name.ilike(pattern))
                .exists()
            )
            conditions.append(
                or_(
                    Book.title.ilike(pattern),
                    Book.isbn.ilike(pattern),
                    Book.synopsis.ilike(pattern),
                    author_match,
                )
            )

        if author_ids:
            conditions.append(
                select(1)
                .select_from(book_authors)
                .where(
                    book_authors.c.isbn == Book.isbn,
                    book_authors.c.author_id.in_(author_ids),
                )
                .exists()
            )

        if genre_ids:
            conditions.append(
                select(1)
                .select_from(book_genres)
                .where(book_genres.c.isbn == Book.isbn, book_genres.c.genre_id.in_(genre_ids))
                .exists()
            )

        if cities:
            # "En esta ciudad" significa reservable hoy: al menos un ejemplar
            # `available` en una sede de esa ciudad. Por eso el resultado cambia con
            # cada reserva, y el controller lo cachea con el TTL de disponibilidad.
            conditions.append(
                select(1)
                .select_from(PhysicalBook.__table__.join(Library, Library.id == PhysicalBook.library_id))
                .where(
                    PhysicalBook.isbn == Book.isbn,
                    PhysicalBook.status == PhysicalBookStatus.available,
                    Library.city.in_(cities),
                )
                .exists()
            )

        return conditions

    def list_filtered(
        self,
        *,
        query: str | None = None,
        author_ids: list[int] | None = None,
        genre_ids: list[int] | None = None,
        cities: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Book], int]:
        """Una página del catálogo filtrado, más el total que matchea (no el de la página)."""
        conditions = self._filters(
            query=query,
            author_ids=author_ids or [],
            genre_ids=genre_ids or [],
            cities=cities or [],
        )
        where = and_(*conditions) if conditions else None

        stmt = select(Book).order_by(Book.title).limit(limit).offset(offset)
        count_stmt = select(func.count()).select_from(Book)
        if where is not None:
            stmt = stmt.where(where)
            count_stmt = count_stmt.where(where)

        return list(self.db.scalars(stmt).all()), self.db.scalar(count_stmt)

    def available_cities(self) -> list[str]:
        """Ciudades con al menos un ejemplar disponible, para poblar el filtro."""
        stmt = (
            select(Library.city)
            .join(PhysicalBook, PhysicalBook.library_id == Library.id)
            .where(PhysicalBook.status == PhysicalBookStatus.available)
            .distinct()
            .order_by(Library.city)
        )
        return list(self.db.scalars(stmt).all())

    def search(self, query: str, limit: int = 50) -> list[Book]:
        pattern = f"%{query}%"
        stmt = (
            select(Book)
            .outerjoin(Book.authors)
            .where(
                or_(
                    Book.title.ilike(pattern),
                    Book.isbn.ilike(pattern),
                    Book.synopsis.ilike(pattern),
                    Author.name.ilike(pattern),
                )
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

    def get(self, isbn: str) -> Book | None:
        return self.db.get(Book, isbn)

    def create(self, book: Book) -> Book:
        self.db.add(book)
        self.db.flush()
        return book

    def delete(self, book: Book) -> None:
        self.db.delete(book)
        self.db.flush()

    def count_physical_books(self, isbn: str) -> int:
        return self.db.scalar(
            select(func.count()).select_from(PhysicalBook).where(PhysicalBook.isbn == isbn)
        )
