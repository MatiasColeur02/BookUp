from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..persistence.database import get_db
from ..services import reservation_service
from . import schemas

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("", response_model=schemas.ReservationOut, status_code=201)
def create_reservation(payload: schemas.ReservationCreate, db: Session = Depends(get_db)):
    return reservation_service.create_reservation(db, **payload.model_dump())


@router.get("", response_model=list[schemas.ReservationOut])
def list_reservations(library_id: int | None = None, db: Session = Depends(get_db)):
    return reservation_service.list_reservations(db, library_id)


@router.patch("/{reservation_id}/pickup", response_model=schemas.ReservationOut)
def mark_picked_up(reservation_id: int, db: Session = Depends(get_db)):
    return reservation_service.mark_picked_up(db, reservation_id)
