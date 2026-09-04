from fastapi import APIRouter, Depends, Query
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


@router.patch("/{reservation_id}/confirm", response_model=schemas.ReservationOut)
def confirm_reservation(
    reservation_id: int,
    librarian: str = Query(..., description="Name of the librarian confirming the reservation"),
    db: Session = Depends(get_db),
):
    return reservation_service.confirm_reservation(db, reservation_id, librarian=librarian)
