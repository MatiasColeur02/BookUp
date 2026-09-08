from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import cache
from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import catalog_service
from . import schemas
from .dependencies import require_roles

router = APIRouter(prefix="/books", tags=["catalog"])

require_staff = require_roles(UserRole.librarian, UserRole.sysadmin)

# Un libro embebe sus autores y géneros, y la disponibilidad embebe al libro: tocar el
# catálogo invalida las dos cosas. La relación inversa (tocar un autor invalida el
# catálogo) está en `author_controller`.
_WRITE_NAMESPACES = (cache.NS_CATALOG, cache.NS_AVAILABILITY)


@router.get("", response_model=schemas.BookPage)
def list_books(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    def load() -> schemas.BookPage:
        books, total = catalog_service.list_books(db, limit=limit, offset=offset)
        return schemas.BookPage(items=books, total=total, limit=limit, offset=offset)

    # La página va en la clave: cada (limit, offset) es una entrada distinta, y todas
    # caen juntas con el `INCR` del namespace cuando se toca el catálogo.
    return cache.cached(
        cache.NS_CATALOG,
        f"books:list:{limit}:{offset}",
        ttl=cache.TTL_CATALOG,
        model=schemas.BookPage,
        loader=load,
    )


@router.post("", response_model=schemas.BookOut, status_code=201)
def create_book(
    payload: schemas.BookCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    book = catalog_service.create_book(db, **payload.model_dump())
    cache.invalidate(*_WRITE_NAMESPACES)
    return book


# Declared before `/{isbn}` so FastAPI does not match "search" as an ISBN.
@router.get("/search", response_model=list[schemas.BookOut])
def search_books(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    # La consulta más cara del MVP: un ILIKE con `%...%` a cuatro columnas, que no usa
    # índice y escanea la tabla entera. Es la que más gana con el cache.
    return cache.cached(
        cache.NS_CATALOG,
        f"books:search:{cache.digest(q)}",
        ttl=cache.TTL_SEARCH,
        model=list[schemas.BookOut],
        loader=lambda: catalog_service.search_books(db, q),
    )


@router.get("/{isbn}", response_model=schemas.BookOut)
def get_book(isbn: str, db: Session = Depends(get_db)):
    return cache.cached(
        cache.NS_CATALOG,
        f"books:{isbn}",
        ttl=cache.TTL_CATALOG,
        model=schemas.BookOut,
        loader=lambda: catalog_service.get_book(db, isbn),
    )


@router.patch("/{isbn}", response_model=schemas.BookOut)
def update_book(
    isbn: str,
    payload: schemas.BookUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    book = catalog_service.update_book(db, isbn, **payload.model_dump(exclude_unset=True))
    cache.invalidate(*_WRITE_NAMESPACES)
    return book


@router.delete("/{isbn}", status_code=204)
def delete_book(
    isbn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    catalog_service.delete_book(db, isbn)
    cache.invalidate(*_WRITE_NAMESPACES)


@router.get("/{isbn}/availability", response_model=schemas.BookAvailability)
def get_availability(isbn: str, db: Session = Depends(get_db)):
    def load() -> schemas.BookAvailability:
        book, rows = catalog_service.get_availability(db, isbn)
        libraries = [
            schemas.LibraryAvailability(
                library=library,
                available_copies=len(physical_books),
                physical_book_id=physical_books[0].id,
            )
            for library, physical_books in rows
        ]
        return schemas.BookAvailability(book=book, libraries=libraries)

    # El stock cruzado de toda la red es la pantalla más visitada y la que más joins
    # cuesta, pero también la que más rápido queda vieja: TTL corto, e invalidación
    # explícita desde reservas y ejemplares.
    return cache.cached(
        cache.NS_AVAILABILITY,
        f"books:{isbn}:availability",
        ttl=cache.TTL_AVAILABILITY,
        model=schemas.BookAvailability,
        loader=load,
    )
