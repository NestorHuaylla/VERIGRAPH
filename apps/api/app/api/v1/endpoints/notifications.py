from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import NotificationDeliveryChannel, NotificationDeliveryStatus
from app.core.dependencies import require_report_reviewer
from app.db.session import get_db
from app.models.user import User
from app.schemas.notification import NotificationListItem, NotificationReadResponse
from app.schemas.notification_metrics import NotificationMetricsResponse
from app.schemas.notification_delivery import (
    NotificationDeliveryListItem,
    NotificationDeliveryStatusResponse,
    NotificationDeliveryStatusUpdate,
)
from app.services.notification_deliveries import NotificationDeliveryNotFoundError
from app.services.notification_deliveries import list_notification_deliveries as list_notification_deliveries_service
from app.services.notification_deliveries import (
    update_notification_delivery_status as update_notification_delivery_status_service,
)
from app.services.notification_metrics import get_notification_metrics as get_notification_metrics_service
from app.services.notifications import NotificationNotFoundError
from app.services.notifications import list_notifications as list_notifications_service
from app.services.notifications import mark_notification_read as mark_notification_read_service

router = APIRouter()


@router.get("", response_model=list[NotificationListItem])
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[NotificationListItem]:
    return await list_notifications_service(db, unread_only=unread_only, limit=limit, offset=offset)


@router.get("/metrics", response_model=NotificationMetricsResponse)
async def get_notification_metrics(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> NotificationMetricsResponse:
    return await get_notification_metrics_service(db)


@router.get("/deliveries", response_model=list[NotificationDeliveryListItem])
async def list_notification_deliveries(
    delivery_status: NotificationDeliveryStatus | None = Query(default=None, alias="status"),
    channel: NotificationDeliveryChannel | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[NotificationDeliveryListItem]:
    return await list_notification_deliveries_service(
        db,
        status_filter=delivery_status,
        channel=channel,
        limit=limit,
        offset=offset,
    )


@router.patch("/deliveries/{delivery_id}/status", response_model=NotificationDeliveryStatusResponse)
async def update_notification_delivery_status(
    delivery_id: UUID,
    payload: NotificationDeliveryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> NotificationDeliveryStatusResponse:
    try:
        delivery = await update_notification_delivery_status_service(db, delivery_id, payload)
    except NotificationDeliveryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification delivery not found.") from exc

    return NotificationDeliveryStatusResponse(
        id=str(delivery.id),
        status=NotificationDeliveryStatus(delivery.status),
        attempts=delivery.attempts,
        message="Estado de delivery actualizado.",
    )


@router.patch("/{notification_id}/read", response_model=NotificationReadResponse)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> NotificationReadResponse:
    try:
        notification = await mark_notification_read_service(db, notification_id)
    except NotificationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.") from exc

    return NotificationReadResponse(
        id=str(notification.id),
        is_read=notification.is_read,
        message="Notificacion marcada como leida.",
    )
