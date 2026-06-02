from datetime import datetime, timezone

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import NotificationDeliveryStatus
from app.models.notification import Notification, NotificationDelivery
from app.schemas.notification_metrics import (
    LastFailedNotificationDelivery,
    NotificationDeliveryChannelMetrics,
    NotificationMetricsResponse,
)


async def get_notification_metrics(db: AsyncSession) -> NotificationMetricsResponse:
    notifications_total, notifications_unread = await get_notification_totals(db)
    notifications_by_severity = await get_notification_severity_counts(db)
    delivery_totals = await get_delivery_totals(db)
    deliveries_by_channel = await get_delivery_channel_metrics(db)
    last_failed_delivery = await get_last_failed_delivery(db)

    return NotificationMetricsResponse(
        notifications_total=notifications_total,
        notifications_unread=notifications_unread,
        notifications_by_severity=notifications_by_severity,
        deliveries_total=delivery_totals["total"],
        deliveries_pending=delivery_totals["pending"],
        deliveries_scheduled=delivery_totals["scheduled"],
        deliveries_due=delivery_totals["due"],
        deliveries_sent=delivery_totals["sent"],
        deliveries_failed=delivery_totals["failed"],
        deliveries_by_channel=deliveries_by_channel,
        last_failed_delivery=last_failed_delivery,
    )


async def get_notification_totals(db: AsyncSession) -> tuple[int, int]:
    result = await db.execute(
        select(
            func.count(Notification.id),
            func.sum(case((Notification.is_read.is_(False), 1), else_=0)),
        )
    )
    total, unread = result.one()
    return int(total or 0), int(unread or 0)


async def get_notification_severity_counts(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(Notification.severity, func.count(Notification.id)).group_by(Notification.severity)
    )
    return {str(severity): int(count or 0) for severity, count in result.all()}


async def get_delivery_totals(db: AsyncSession) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(
            func.count(NotificationDelivery.id),
            func.sum(case((NotificationDelivery.status == NotificationDeliveryStatus.PENDING.value, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            NotificationDelivery.status == NotificationDeliveryStatus.PENDING.value,
                            NotificationDelivery.next_attempt_at.is_not(None),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        and_(
                            NotificationDelivery.status == NotificationDeliveryStatus.PENDING.value,
                            NotificationDelivery.next_attempt_at.is_not(None),
                            NotificationDelivery.next_attempt_at <= now,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((NotificationDelivery.status == NotificationDeliveryStatus.SENT.value, 1), else_=0)),
            func.sum(case((NotificationDelivery.status == NotificationDeliveryStatus.FAILED.value, 1), else_=0)),
        )
    )
    total, pending, scheduled, due, sent, failed = result.one()
    return {
        "total": int(total or 0),
        "pending": int(pending or 0),
        "scheduled": int(scheduled or 0),
        "due": int(due or 0),
        "sent": int(sent or 0),
        "failed": int(failed or 0),
    }


async def get_delivery_channel_metrics(db: AsyncSession) -> list[NotificationDeliveryChannelMetrics]:
    result = await db.execute(
        select(
            NotificationDelivery.channel,
            func.count(NotificationDelivery.id),
            func.sum(case((NotificationDelivery.status == NotificationDeliveryStatus.PENDING.value, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            NotificationDelivery.status == NotificationDeliveryStatus.PENDING.value,
                            NotificationDelivery.next_attempt_at.is_not(None),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((NotificationDelivery.status == NotificationDeliveryStatus.SENT.value, 1), else_=0)),
            func.sum(case((NotificationDelivery.status == NotificationDeliveryStatus.FAILED.value, 1), else_=0)),
        ).group_by(NotificationDelivery.channel)
        .order_by(NotificationDelivery.channel.asc())
    )

    metrics: list[NotificationDeliveryChannelMetrics] = []
    for channel, total, pending, scheduled, sent, failed in result.all():
        metrics.append(
            NotificationDeliveryChannelMetrics(
                channel=channel,
                total=int(total or 0),
                pending=int(pending or 0),
                scheduled=int(scheduled or 0),
                sent=int(sent or 0),
                failed=int(failed or 0),
            )
        )
    return metrics


async def get_last_failed_delivery(db: AsyncSession) -> LastFailedNotificationDelivery | None:
    result = await db.execute(
        select(NotificationDelivery)
        .where(NotificationDelivery.status == NotificationDeliveryStatus.FAILED.value)
        .order_by(desc(NotificationDelivery.created_at))
        .limit(1)
    )
    delivery = result.scalar_one_or_none()
    if delivery is None:
        return None

    return LastFailedNotificationDelivery(
        id=str(delivery.id),
        notification_id=str(delivery.notification_id),
        channel=delivery.channel,
        destination=delivery.destination,
        attempts=delivery.attempts,
        last_error=delivery.last_error,
        status=delivery.status,
        next_attempt_at=delivery.next_attempt_at,
        created_at=delivery.created_at,
    )
