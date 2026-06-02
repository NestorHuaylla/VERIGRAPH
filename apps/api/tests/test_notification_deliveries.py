import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.constants import NotificationDeliveryChannel, NotificationDeliveryStatus, NotificationSeverity
from app.models.notification import Notification, NotificationDelivery
from app.schemas.notification_delivery import NotificationDeliveryStatusUpdate
from app.services.notification_deliveries import (
    NotificationDeliveryNotFoundError,
    NotificationDeliveryRoute,
    apply_notification_delivery_status_update,
    apply_notification_delivery_retry_schedule,
    build_notification_delivery,
    build_notification_delivery_list_item,
    calculate_notification_delivery_next_attempt_at,
    create_notification_deliveries,
    list_notification_deliveries,
    update_notification_delivery_status,
)


class FakeScalarOneResult:
    def __init__(self, item: object | None) -> None:
        self.item = item

    def scalar_one_or_none(self) -> object | None:
        return self.item


class FakeScalarManyResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> "FakeScalarManyResult":
        return self

    def all(self) -> list[object]:
        return self.items


class FakeDeliverySession:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.objects: list[object] = []
        self.committed = False
        self.refreshed: object | None = None

    async def execute(self, statement: object) -> object:
        self.statement = statement
        return self.results.pop(0)

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        self.refreshed = obj


def build_notification() -> Notification:
    notification = Notification(
        user_id=None,
        event_type="case.critical",
        title="Expediente critico detectado",
        message="El expediente quedo en nivel critical.",
        severity=NotificationSeverity.CRITICAL.value,
        is_read=False,
        metadata_json={},
    )
    notification.id = uuid4()
    notification.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    notification.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return notification


def build_delivery(notification: Notification | None = None) -> NotificationDelivery:
    notification = notification or build_notification()
    delivery = build_notification_delivery(
        notification,
        channel=NotificationDeliveryChannel.WEBHOOK,
    )
    delivery.id = uuid4()
    delivery.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    delivery.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return delivery


def test_build_notification_delivery_starts_pending() -> None:
    notification = build_notification()

    delivery = build_notification_delivery(
        notification,
        channel=NotificationDeliveryChannel.WEBHOOK,
    )

    assert delivery.notification_id == notification.id
    assert delivery.channel == NotificationDeliveryChannel.WEBHOOK.value
    assert delivery.destination is None
    assert delivery.status == NotificationDeliveryStatus.PENDING.value
    assert delivery.attempts == 0
    assert delivery.metadata_json["notification_event_type"] == "case.critical"


def test_create_notification_deliveries_adds_routes_without_commit() -> None:
    notification = build_notification()
    session = FakeDeliverySession([])

    deliveries = asyncio.run(
        create_notification_deliveries(
            session,  # type: ignore[arg-type]
            notification,
            routes=(
                NotificationDeliveryRoute(channel=NotificationDeliveryChannel.EMAIL, destination="alerts@example.com"),
                NotificationDeliveryRoute(channel=NotificationDeliveryChannel.SLACK, destination="#fraud-alerts"),
            ),
        )
    )

    assert session.committed is False
    assert session.objects == deliveries
    assert [delivery.channel for delivery in deliveries] == ["email", "slack"]
    assert deliveries[0].destination == "alerts@example.com"
    assert deliveries[1].destination == "#fraud-alerts"


def test_list_notification_deliveries_returns_items() -> None:
    delivery = build_delivery()
    session = FakeDeliverySession([FakeScalarManyResult([delivery])])

    response = asyncio.run(
        list_notification_deliveries(
            session,  # type: ignore[arg-type]
            status_filter=NotificationDeliveryStatus.PENDING,
            channel=NotificationDeliveryChannel.WEBHOOK,
        )
    )

    assert len(response) == 1
    assert response[0].id == str(delivery.id)
    assert response[0].status == NotificationDeliveryStatus.PENDING
    assert response[0].channel == NotificationDeliveryChannel.WEBHOOK
    assert response[0].next_attempt_at is None


def test_build_notification_delivery_list_item_maps_model_to_schema() -> None:
    delivery = build_delivery()

    item = build_notification_delivery_list_item(delivery)

    assert item.id == str(delivery.id)
    assert item.notification_id == str(delivery.notification_id)
    assert item.channel == NotificationDeliveryChannel.WEBHOOK
    assert item.status == NotificationDeliveryStatus.PENDING
    assert item.next_attempt_at is None


def test_apply_notification_delivery_status_update_marks_sent() -> None:
    delivery = build_delivery()

    apply_notification_delivery_status_update(
        delivery,
        NotificationDeliveryStatusUpdate(status=NotificationDeliveryStatus.SENT),
    )

    assert delivery.status == NotificationDeliveryStatus.SENT.value
    assert delivery.sent_at is not None
    assert delivery.last_error is None
    assert delivery.attempts == 0


def test_apply_notification_delivery_status_update_marks_failed_and_increments_attempts() -> None:
    delivery = build_delivery()

    apply_notification_delivery_status_update(
        delivery,
        NotificationDeliveryStatusUpdate(status=NotificationDeliveryStatus.FAILED, error="Webhook timeout."),
    )

    assert delivery.status == NotificationDeliveryStatus.FAILED.value
    assert delivery.attempts == 1
    assert delivery.last_error == "Webhook timeout."
    assert delivery.next_attempt_at is None


def test_update_notification_delivery_status_commits() -> None:
    delivery = build_delivery()
    session = FakeDeliverySession([FakeScalarOneResult(delivery)])

    response = asyncio.run(
        update_notification_delivery_status(
            session,  # type: ignore[arg-type]
            delivery.id,
            NotificationDeliveryStatusUpdate(status=NotificationDeliveryStatus.SENT),
        )
    )

    assert response is delivery
    assert delivery.status == NotificationDeliveryStatus.SENT.value
    assert session.committed is True
    assert session.refreshed is delivery


def test_update_notification_delivery_status_raises_when_missing() -> None:
    session = FakeDeliverySession([FakeScalarOneResult(None)])

    with pytest.raises(NotificationDeliveryNotFoundError):
        asyncio.run(
            update_notification_delivery_status(
                session,  # type: ignore[arg-type]
                uuid4(),
                NotificationDeliveryStatusUpdate(status=NotificationDeliveryStatus.SENT),
            )
        )

    assert session.committed is False


def test_calculate_notification_delivery_next_attempt_at_uses_backoff() -> None:
    first = calculate_notification_delivery_next_attempt_at(1)
    second = calculate_notification_delivery_next_attempt_at(2)

    assert second > first


def test_apply_notification_delivery_retry_schedule_keeps_retryable_deliveries_pending() -> None:
    delivery = build_delivery()

    retry_scheduled = apply_notification_delivery_retry_schedule(delivery, error="Webhook timeout.")

    assert retry_scheduled is True
    assert delivery.status == NotificationDeliveryStatus.PENDING.value
    assert delivery.attempts == 1
    assert delivery.next_attempt_at is not None
    assert delivery.last_error == "Webhook timeout."


def test_apply_notification_delivery_retry_schedule_marks_failed_after_max_attempts() -> None:
    delivery = build_delivery()
    delivery.attempts = 2

    retry_scheduled = apply_notification_delivery_retry_schedule(delivery, error="Webhook timeout.")

    assert retry_scheduled is False
    assert delivery.status == NotificationDeliveryStatus.FAILED.value
    assert delivery.attempts == 3
    assert delivery.next_attempt_at is None
