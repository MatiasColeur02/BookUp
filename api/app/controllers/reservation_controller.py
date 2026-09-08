from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import cache
from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import reservation_service
from . import schemas
from .dependencies import get_current_user, require_roles

router = APIRouter(prefix="/reservations", tags=["reservations"])

require_staff = require_roles(UserRole.librarian, UserRole.sysadmin)


# Nada de este router se cachea: la respuesta depende del rol y del usuario del token
# (un customer ve las suyas, un librarian las de su sede), así que una entrada compartida
# filtraría reservas de una persona a otra. Lo que sí hacen las transiciones que mueven
# el `status` del ejemplar es invalidar la disponibilidad pública.
@router.post("", response_model=schemas.ReservationOut, status_code=201)
def create_reservation(
    payload: schemas.ReservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reservation = reservation_service.create_reservation(
        db, user=current_user, **payload.model_dump()
    )
    # available -> reserved: el ejemplar deja de estar disponible.
    cache.invalidate(cache.NS_AVAILABILITY)
    return reservation


@router.get("", response_model=list[schemas.ReservationOut])
def list_reservations(
    library_id: int | None = None,
    is_open: bool | None = None,
    mine: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return reservation_service.list_reservations(
        db, viewer=current_user, library_id=library_id, is_open=is_open, mine=mine
    )


# Declared before `/{reservation_id}` so "expire" is not read as an id.
@router.post("/expire", response_model=schemas.ExpiredReservations)
def expire_reservations(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.sysadmin)),
):
    expired = reservation_service.expire_reservations(db)
    # reserved -> available en cada reserva vencida sin retirar.
    if expired:
        cache.invalidate(cache.NS_AVAILABILITY)
    return schemas.ExpiredReservations(expired=expired)


@router.get("/{reservation_id}", response_model=schemas.ReservationOut)
def get_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return reservation_service.get_reservation(db, reservation_id, viewer=current_user)


@router.patch("/{reservation_id}", response_model=schemas.ReservationOut)
def update_reservation(
    reservation_id: int,
    payload: schemas.ReservationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return reservation_service.update_reservation(
        db, reservation_id, viewer=current_user, **payload.model_dump(exclude_unset=True)
    )


# `pickup` (reserved -> loaned) y `PATCH /{id}` (solo mueve `expires_at`) no invalidan:
# la disponibilidad lista únicamente los ejemplares `available`, y ninguna de las dos
# transiciones entra ni sale de ese conjunto.
@router.patch("/{reservation_id}/pickup", response_model=schemas.ReservationOut)
def mark_picked_up(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    return reservation_service.mark_picked_up(db, reservation_id, viewer=current_user)


@router.patch("/{reservation_id}/return", response_model=schemas.ReservationOut)
def mark_returned(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    reservation = reservation_service.mark_returned(db, reservation_id, viewer=current_user)
    # loaned -> available: el ejemplar vuelve al stock.
    cache.invalidate(cache.NS_AVAILABILITY)
    return reservation


@router.post("/{reservation_id}/cancel", response_model=schemas.ReservationOut)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reservation = reservation_service.cancel_reservation(db, reservation_id, viewer=current_user)
    # reserved -> available: el ejemplar vuelve al stock.
    cache.invalidate(cache.NS_AVAILABILITY)
    return reservation
