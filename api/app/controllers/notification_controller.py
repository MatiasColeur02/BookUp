from fastapi import APIRouter, Depends, Path, Query

from ..persistence.dynamo import Dynamo, get_db
from ..persistence.entities import User
from ..services import notification_service
from ..services.notification_service import Scope
from . import schemas
from .dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])

# El id y el cursor son la SK de DynamoDB en base64url: con una fecha y un event_id rondan los
# 100 caracteres. El techo es para no decodificar lo que mande cualquiera.
MAX_REFERENCE_LENGTH = 512
MAX_PAGE = 50


# Nada de esto se cachea ni tiene rate limit (`notifications-roadmap.md` §6.3): la respuesta
# depende del usuario del token, y el polling es tráfico autenticado y acotado. Las escrituras
# tampoco invalidan nada: ningún esquema cacheado embebe notificaciones.
@router.get("", response_model=schemas.NotificationPage)
def list_notifications(
    scope: Scope = Scope.me,
    limit: int = Query(20, ge=1, le=MAX_PAGE),
    cursor: str | None = Query(None, min_length=1, max_length=MAX_REFERENCE_LENGTH),
    db: Dynamo = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, next_cursor = notification_service.list_inbox(
        db, viewer=current_user, scope=scope, limit=limit, cursor=cursor
    )
    return schemas.NotificationPage(
        items=[schemas.NotificationOut.model_validate(n) for n in items], next_cursor=next_cursor
    )


@router.get("/unread-count", response_model=schemas.UnreadCounts)
def unread_count(
    db: Dynamo = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return notification_service.unread_counts(db, viewer=current_user)


@router.patch("/{scope}/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(
    scope: Scope,
    notification_id: str = Path(min_length=1, max_length=MAX_REFERENCE_LENGTH),
    db: Dynamo = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return notification_service.mark_read(
        db, viewer=current_user, scope=scope, notification_id=notification_id
    )


@router.post("/{scope}/read-all", response_model=schemas.MarkedNotifications)
def mark_all_read(
    scope: Scope,
    db: Dynamo = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    marked = notification_service.mark_all_read(db, viewer=current_user, scope=scope)
    return schemas.MarkedNotifications(marked=marked)
