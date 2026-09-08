from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import cache
from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import author_service
from . import schemas
from .dependencies import require_roles

router = APIRouter(prefix="/authors", tags=["authors"])

require_staff = require_roles(UserRole.librarian, UserRole.sysadmin)

# Renombrar un autor cambia el `BookOut` de cada libro suyo, y con él la disponibilidad,
# que lo embebe: por eso una escritura acá arrastra tres namespaces.
_WRITE_NAMESPACES = (cache.NS_AUTHORS, cache.NS_CATALOG, cache.NS_AVAILABILITY)


@router.get("", response_model=list[schemas.AuthorOut])
def list_authors(db: Session = Depends(get_db)):
    return cache.cached(
        cache.NS_AUTHORS,
        "authors:list",
        ttl=cache.TTL_REFERENCE,
        model=list[schemas.AuthorOut],
        loader=lambda: author_service.list_authors(db),
    )


@router.post("", response_model=schemas.AuthorOut, status_code=201)
def create_author(
    payload: schemas.AuthorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    author = author_service.create_author(db, **payload.model_dump())
    cache.invalidate(*_WRITE_NAMESPACES)
    return author


@router.get("/{author_id}", response_model=schemas.AuthorOut)
def get_author(author_id: int, db: Session = Depends(get_db)):
    return cache.cached(
        cache.NS_AUTHORS,
        f"authors:{author_id}",
        ttl=cache.TTL_REFERENCE,
        model=schemas.AuthorOut,
        loader=lambda: author_service.get_author(db, author_id),
    )


@router.patch("/{author_id}", response_model=schemas.AuthorOut)
def update_author(
    author_id: int,
    payload: schemas.AuthorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    author = author_service.update_author(
        db, author_id, **payload.model_dump(exclude_unset=True)
    )
    cache.invalidate(*_WRITE_NAMESPACES)
    return author


@router.delete("/{author_id}", status_code=204)
def delete_author(
    author_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    author_service.delete_author(db, author_id)
    cache.invalidate(*_WRITE_NAMESPACES)
