import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.core.constants import NotificationDeliveryStatus, NotificationSeverity
from app.models.notification import Notification, NotificationDelivery
from app.services.notification_metrics import (
    get_delivery_channel_metrics,
    get_delivery_totals,
    get_last_failed_delivery,
    get_notification_metrics,
    get_notification_severity_counts,
    get_notification_totals,
)


class FakeOneResult:
    def __init__(self, row: object | None) -> None:
        self.row = row

    def one(self) -> object:
        return self.row

    def scalar_one_or_none(self) -> object | None:
        return self.row


class FakeManyResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakeMetricsSession:
    def __init__(self, results: list[object]) -> None:
        self.results = results

    async def execute(self, statement: object) -> object:
        self.statement = statement
        return self.results.pop(0)


def build_notification(severity: str = NotificationSeverity.WARNING.value) -> Notification:
    notification = Notification(
        user_id=None,
        event_type="report.high_risk",
        title="Reporte de alto riesgo recibido",
        message="El reporte quedo en nivel high.",
        severity=severity,
        is_read=False,
        metadata_json={},
    )
    notification.id = uuid4()
    notification.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    notification.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return notification


def build_failed_delivery() -> NotificationDelivery:
    delivery = NotificationDelivery(
        notification_id=uuid4(),
        channel="webhook",
        destination="https://example.test/webhook",
        status=NotificationDeliveryStatus.FAILED.value,
        attempts=3,
        last_error="Webhook returned HTTP 500: server error",
        sent_at=None,
        next_attempt_at=None,
        metadata_json={},
    )
    delivery.id = uuid4()
    delivery.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    delivery.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return delivery


def test_get_notification_totals_counts_read_and_unread() -> None:
    session = FakeMetricsSession([FakeOneResult((12, 5))])

    total, unread = asyncio.run(get_notification_totals(session))  # type: ignore[arg-type]

    assert total == 12
    assert unread == 5


def test_get_notification_severity_counts_groups_by_severity() -> None:
    session = FakeMetricsSession([FakeManyResult([("warning", 3), ("critical", 1)])])

    counts = asyncio.run(get_notification_severity_counts(session))  # type: ignore[arg-type]

    assert counts == {"warning": 3, "critical": 1}


def test_get_delivery_totals_counts_statuses_and_due_retries() -> None:
    session = FakeMetricsSession([FakeOneResult((20, 8, 4, 2, 6, 4))])

    totals = asyncio.run(get_delivery_totals(session))  # type: ignore[arg-type]

    assert totals == {
        "total": 20,
        "pending": 8,
        "scheduled": 4,
        "due": 2,
        "sent": 6,
        "failed": 4,
    }


def test_get_delivery_channel_metrics_groups_counts() -> None:
    session = FakeMetricsSession(
        [FakeManyResult([("webhook", 10, 4, 2, 3, 3), ("email", 4, 1, 1, 2, 1)])]
    )

    metrics = asyncio.run(get_delivery_channel_metrics(session))  # type: ignore[arg-type]

    assert len(metrics) == 2
    assert metrics[0].channel == "webhook"
    assert metrics[0].total == 10
    assert metrics[0].scheduled == 2
    assert metrics[1].channel == "email"
    assert metrics[1].failed == 1


def test_get_last_failed_delivery_returns_latest_failed_row() -> None:
    delivery = build_failed_delivery()
    session = FakeMetricsSession([FakeOneResult(delivery)])

    result = asyncio.run(get_last_failed_delivery(session))  # type: ignore[arg-type]

    assert result is not None
    assert result.id == str(delivery.id)
    assert result.channel == "webhook"
    assert result.last_error == "Webhook returned HTTP 500: server error"


def test_get_notification_metrics_returns_operational_summary() -> None:
    delivery = build_failed_delivery()
    session = FakeMetricsSession(
        [
            FakeOneResult((12, 5)),
            FakeManyResult([("warning", 3), ("critical", 1)]),
            FakeOneResult((20, 8, 4, 2, 6, 4)),
            FakeManyResult([("webhook", 10, 4, 2, 3, 3)]),
            FakeOneResult(delivery),
        ]
    )

    result = asyncio.run(get_notification_metrics(session))  # type: ignore[arg-type]

    assert result.notifications_total == 12
    assert result.notifications_unread == 5
    assert result.notifications_by_severity == {"warning": 3, "critical": 1}
    assert result.deliveries_total == 20
    assert result.deliveries_pending == 8
    assert result.deliveries_scheduled == 4
    assert result.deliveries_due == 2
    assert result.deliveries_sent == 6
    assert result.deliveries_failed == 4
    assert result.deliveries_by_channel[0].channel == "webhook"
    assert result.last_failed_delivery is not None
    assert result.last_failed_delivery.id == str(delivery.id)
