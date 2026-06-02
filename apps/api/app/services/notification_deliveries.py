from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    MAX_NOTIFICATION_DELIVERY_ATTEMPTS,
    NOTIFICATION_DELIVERY_BACKOFF_BASE_SECONDS,
    NOTIFICATION_DELIVERY_BACKOFF_MAX_SECONDS,
    NotificationDeliveryChannel,
    NotificationDeliveryStatus,
)
from app.core.config import settings
from app.models.notification import Notification, NotificationDelivery
from app.schemas.notification_delivery import NotificationDeliveryListItem, NotificationDeliveryStatusUpdate


DEFAULT_NOTIFICATION_DELIVERY_LIMIT = 100


@dataclass(frozen=True)
class NotificationDeliveryRoute:
    channel: NotificationDeliveryChannel
    destination: str | None = None


class NotificationDeliveryNotFoundError(Exception):
    def __init__(self, delivery_id: UUID) -> None:
        super().__init__(f"Notification delivery {delivery_id} was not found.")
        self.delivery_id = delivery_id


async def create_default_notification_deliveries(
    db: AsyncSession,
    notification: Notification,
) -> list[NotificationDelivery]:
    return await create_notification_deliveries(
        db,
        notification,
        routes=build_default_notification_delivery_routes(),
    )


def build_default_notification_delivery_routes() -> tuple[NotificationDeliveryRoute, ...]:
    routes: list[NotificationDeliveryRoute] = []
    if settings.notification_webhook_url:
        routes.append(
            NotificationDeliveryRoute(
                channel=NotificationDeliveryChannel.WEBHOOK,
                destination=settings.notification_webhook_url,
            )
        )
    if settings.slack_webhook_url:
        routes.append(
            NotificationDeliveryRoute(
                channel=NotificationDeliveryChannel.SLACK,
                destination=settings.slack_webhook_url,
            )
        )
    if settings.alert_email_to:
        routes.append(
            NotificationDeliveryRoute(
                channel=NotificationDeliveryChannel.EMAIL,
                destination=settings.alert_email_to,
            )
        )
    if not routes:
        routes.append(NotificationDeliveryRoute(channel=NotificationDeliveryChannel.WEBHOOK))
    return tuple(routes)


async def create_notification_deliveries(
    db: AsyncSession,
    notification: Notification,
    *,
    routes: tuple[NotificationDeliveryRoute, ...],
) -> list[NotificationDelivery]:
    ensure_notification_id(notification)
    deliveries = [
        build_notification_delivery(
            notification,
            channel=route.channel,
            destination=route.destination,
        )
        for route in routes
    ]
    for delivery in deliveries:
        db.add(delivery)
    return deliveries


async def list_notification_deliveries(
    db: AsyncSession,
    *,
    status_filter: NotificationDeliveryStatus | None = None,
    channel: NotificationDeliveryChannel | None = None,
    limit: int = DEFAULT_NOTIFICATION_DELIVERY_LIMIT,
    offset: int = 0,
) -> list[NotificationDeliveryListItem]:
    statement = select(NotificationDelivery).order_by(desc(NotificationDelivery.created_at)).limit(limit).offset(offset)
    if status_filter is not None:
        statement = statement.where(NotificationDelivery.status == status_filter.value)
    if channel is not None:
        statement = statement.where(NotificationDelivery.channel == channel.value)

    result = await db.execute(statement)
    return [build_notification_delivery_list_item(delivery) for delivery in result.scalars().all()]


async def update_notification_delivery_status(
    db: AsyncSession,
    delivery_id: UUID,
    payload: NotificationDeliveryStatusUpdate,
) -> NotificationDelivery:
    delivery = await find_notification_delivery_by_id(db, delivery_id)
    if delivery is None:
        raise NotificationDeliveryNotFoundError(delivery_id)

    apply_notification_delivery_status_update(delivery, payload)
    await db.commit()
    await db.refresh(delivery)

    return delivery


async def find_notification_delivery_by_id(db: AsyncSession, delivery_id: UUID) -> NotificationDelivery | None:
    result = await db.execute(select(NotificationDelivery).where(NotificationDelivery.id == delivery_id))
    return result.scalar_one_or_none()


def build_notification_delivery(
    notification: Notification,
    *,
    channel: NotificationDeliveryChannel,
    destination: str | None = None,
) -> NotificationDelivery:
    return NotificationDelivery(
        notification_id=notification.id,
        channel=channel.value,
        destination=destination,
        status=NotificationDeliveryStatus.PENDING.value,
        attempts=0,
        last_error=None,
        sent_at=None,
        next_attempt_at=None,
        metadata_json={
            "notification_event_type": notification.event_type,
            "notification_severity": notification.severity,
            "notification_title": notification.title,
            "notification_message": notification.message,
            "notification_metadata": notification.metadata_json or {},
            "route": "default",
            "delivery_engine": "outbox",
        },
    )


def build_notification_delivery_list_item(delivery: NotificationDelivery) -> NotificationDeliveryListItem:
    return NotificationDeliveryListItem(
        id=str(delivery.id),
        notification_id=str(delivery.notification_id),
        channel=NotificationDeliveryChannel(delivery.channel),
        destination=delivery.destination,
        status=NotificationDeliveryStatus(delivery.status),
        attempts=delivery.attempts,
        last_error=delivery.last_error,
        sent_at=delivery.sent_at,
        next_attempt_at=delivery.next_attempt_at,
        metadata=delivery.metadata_json or {},
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
    )


def apply_notification_delivery_status_update(
    delivery: NotificationDelivery,
    payload: NotificationDeliveryStatusUpdate,
) -> None:
    delivery.status = payload.status.value

    if payload.status == NotificationDeliveryStatus.SENT:
        delivery.sent_at = datetime.now(timezone.utc)
        delivery.last_error = None
        delivery.next_attempt_at = None
        return

    if payload.status == NotificationDeliveryStatus.FAILED:
        delivery.attempts += 1
        delivery.last_error = payload.error or "Delivery failed without error detail."
        delivery.next_attempt_at = None
        return

    delivery.sent_at = None
    delivery.last_error = payload.error
    delivery.next_attempt_at = None


def apply_notification_delivery_retry_schedule(delivery: NotificationDelivery, *, error: str) -> bool:
    delivery.attempts += 1
    delivery.last_error = error
    delivery.sent_at = None

    if delivery.attempts >= MAX_NOTIFICATION_DELIVERY_ATTEMPTS:
        delivery.status = NotificationDeliveryStatus.FAILED.value
        delivery.next_attempt_at = None
        return False

    delivery.status = NotificationDeliveryStatus.PENDING.value
    delivery.next_attempt_at = calculate_notification_delivery_next_attempt_at(delivery.attempts)
    return True


def calculate_notification_delivery_next_attempt_at(attempts: int) -> datetime:
    backoff_seconds = NOTIFICATION_DELIVERY_BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0))
    backoff_seconds = min(backoff_seconds, NOTIFICATION_DELIVERY_BACKOFF_MAX_SECONDS)
    return datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)


def ensure_notification_id(notification: Notification) -> None:
    if getattr(notification, "id", None) is None:
        notification.id = uuid4()
