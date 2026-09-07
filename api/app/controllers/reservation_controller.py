from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..persistence.models import User, UserRole
from ..services import reservation_service
from . import schemas
from .dependencies import get_current_user, require_roles

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("", response_model=schemas.ReservationOut, status_code=201)
def create_reservation(
    payload: schemas.ReservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return reservation_service.create_reservation(
        db, user=current_user, **payload.model_dump()
    )


@router.get("", response_model=list[schemas.ReservationOut])
def list_reservations(
    library_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return reservation_service.list_reservations(db, viewer=current_user, library_id=library_id)


@router.get("/{reservation_id}", response_model=schemas.ReservationOut)
def get_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return reservation_service.get_reservation(db, reservation_id, viewer=current_user)


@router.patch("/{reservation_id}/pickup", response_model=schemas.ReservationOut)
def mark_picked_up(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.librarian, UserRole.sysadmin)),
):
    return reservation_service.mark_picked_up(db, reservation_id, viewer=current_user)
