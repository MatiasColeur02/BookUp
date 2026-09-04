from sqlalchemy.orm import Session

from ..persistence.models import CopyStatus, Reservation, ReservationStatus
from ..persistence.repositories import CopyRepository, ReservationRepository
from .errors import ConflictError, NotFoundError


def create_reservation(db: Session, *, copy_id: int, patron_name: str, patron_email: str) -> Reservation:
    copy_repo = CopyRepository(db)
    copy = copy_repo.get(copy_id)
    if copy is None:
        raise NotFoundError(f"Copy {copy_id} not found")
    if copy.status != CopyStatus.available:
        raise ConflictError(f"Copy {copy_id} is not available")

    copy.status = CopyStatus.reserved
    reservation = ReservationRepository(db).create(
        Reservation(copy_id=copy_id, patron_name=patron_name, patron_email=patron_email)
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def list_reservations(db: Session, library_id: int | None = None) -> list[Reservation]:
    return ReservationRepository(db).list(library_id)


def confirm_reservation(db: Session, reservation_id: int, *, librarian: str) -> Reservation:
    # TODO: replace `librarian` (free-text) with the authenticated librarian
    # once the librarian portal has auth (Cognito-backed, per the target
    # architecture).
    repo = ReservationRepository(db)
    reservation = repo.get(reservation_id)
    if reservation is None:
        raise NotFoundError(f"Reservation {reservation_id} not found")

    reservation.status = ReservationStatus.confirmed
    reservation.confirmed_by = librarian
    db.commit()
    db.refresh(reservation)
    return reservation
