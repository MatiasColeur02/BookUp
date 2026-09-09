from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import cache, storage
from ..config import settings
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
        items = [schemas.BookOut.from_book(book) for book in books]
        return schemas.BookPage(items=items, total=total, limit=limit, offset=offset)

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
    return schemas.BookOut.from_book(book)


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
        loader=lambda: [
            schemas.BookOut.from_book(book) for book in catalog_service.search_books(db, q)
        ],
    )


@router.get("/{isbn}", response_model=schemas.BookOut)
def get_book(isbn: str, db: Session = Depends(get_db)):
    return cache.cached(
        cache.NS_CATALOG,
        f"books:{isbn}",
        ttl=cache.TTL_CATALOG,
        model=schemas.BookOut,
        loader=lambda: schemas.BookOut.from_book(catalog_service.get_book(db, isbn)),
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
    return schemas.BookOut.from_book(book)


@router.delete("/{isbn}", status_code=204)
def delete_book(
    isbn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    # La key se lee antes: después del delete la fila ya no está.
    cover_key = catalog_service.get_book(db, isbn).cover_key
    catalog_service.delete_book(db, isbn)
    storage.delete(cover_key)
    cache.invalidate(*_WRITE_NAMESPACES)


def _require_storage() -> None:
    """503 y no 500: sin bucket configurado la feature está apagada, no rota."""
    if not storage.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="El almacenamiento de portadas no está configurado (falta S3_BUCKET).",
        )


@router.post("/{isbn}/cover-upload", response_model=schemas.CoverUploadOut)
def request_cover_upload(
    isbn: str,
    payload: schemas.CoverUploadRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Firma una URL para que el browser haga el `PUT` del archivo directo a S3.

    El archivo no pasa por la API: en la arquitectura target eso evita ocupar una tarea
    de ECS (o el payload de API Gateway, con su tope de 10 MB) para mover una imagen.
    """
    _require_storage()
    # 404 antes de firmar nada: no tiene sentido subir la portada de un libro que no está.
    catalog_service.get_book(db, isbn)

    if payload.content_type not in storage.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Formato no soportado. Se aceptan: {', '.join(storage.ALLOWED_CONTENT_TYPES)}.",
        )
    if payload.size > settings.cover_max_bytes:
        raise HTTPException(
            status_code=422,
            detail=f"La portada no puede superar {settings.cover_max_bytes // (1024 * 1024)} MB.",
        )

    key = storage.build_key(isbn, payload.content_type)
    return schemas.CoverUploadOut(
        upload_url=storage.presign_upload(key, payload.content_type),
        key=key,
        content_type=payload.content_type,
        expires_in=settings.s3_presign_expire_seconds,
    )


@router.put("/{isbn}/cover", response_model=schemas.BookOut)
def attach_cover(
    isbn: str,
    payload: schemas.CoverAttach,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Confirma la key subida y la guarda en la fila del libro."""
    _require_storage()

    # La key la propone el cliente, así que se valida dos veces: que sea del prefijo de
    # este libro (no se puede apuntar la portada a un objeto ajeno) y que exista de
    # verdad — si el PUT del browser falló, la fila quedaría con una imagen rota.
    if not storage.owns_key(isbn, payload.key):
        raise HTTPException(status_code=422, detail="La key no corresponde a este libro.")
    if not storage.exists(payload.key):
        raise HTTPException(
            status_code=422, detail="La portada no está en el bucket: reintentá la subida."
        )

    book, previous_key = catalog_service.set_cover(db, isbn, payload.key)
    if previous_key and previous_key != payload.key:
        storage.delete(previous_key)
    cache.invalidate(*_WRITE_NAMESPACES)
    return schemas.BookOut.from_book(book)


@router.delete("/{isbn}/cover", response_model=schemas.BookOut)
def remove_cover(
    isbn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    book, previous_key = catalog_service.set_cover(db, isbn, None)
    storage.delete(previous_key)
    cache.invalidate(*_WRITE_NAMESPACES)
    return schemas.BookOut.from_book(book)


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
        return schemas.BookAvailability(book=schemas.BookOut.from_book(book), libraries=libraries)

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
