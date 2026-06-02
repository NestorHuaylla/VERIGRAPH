import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.core.constants import NotificationDeliveryChannel, NotificationDeliveryStatus, NotificationSeverity
from app.models.notification import Notification
from app.scripts.process_notification_deliveries import parse_args
from app.services.delivery_worker import (
    build_email_message,
    build_slack_payload,
    build_delivery_worker_run_result,
    build_webhook_payload,
    dispatch_notification_delivery,
    list_pending_notification_delivery_models,
    process_notification_delivery,
    process_pending_notification_deliveries,
)
from app.services.notification_deliveries import build_notification_delivery


class FakeScalarManyResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> "FakeScalarManyResult":
        return self

    def all(self) -> list[object]:
        return self.items


class FakeWorkerSession:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.committed = False

    async def execute(self, statement: object) -> object:
        self.statement = statement
        return self.results.pop(0)

    async def commit(self) -> None:
        self.committed = True


class FakeHttpResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeHttpClient:
    def __init__(self, response: FakeHttpResponse) -> None:
        self.response = response
        self.posts: list[dict[str, object]] = []

    async def post(self, url: str, *, json: dict[str, object]) -> FakeHttpResponse:
        self.posts.append({"url": url, "json": json})
        return self.response


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


def build_delivery(channel: str = NotificationDeliveryChannel.WEBHOOK.value):
    delivery = build_notification_delivery(
        build_notification(),
        channel=NotificationDeliveryChannel.WEBHOOK,
    )
    delivery.id = uuid4()
    delivery.channel = channel
    if channel == NotificationDeliveryChannel.WEBHOOK.value:
        delivery.destination = "https://example.test/verigraph-webhook"
    if channel == NotificationDeliveryChannel.SLACK.value:
        delivery.destination = "https://hooks.slack.test/verigraph"
    if channel == NotificationDeliveryChannel.EMAIL.value:
        delivery.destination = "alerts@example.test"
    delivery.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    delivery.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return delivery


def test_list_pending_notification_delivery_models_returns_pending_batch() -> None:
    delivery = build_delivery()
    session = FakeWorkerSession([FakeScalarManyResult([delivery])])

    response = asyncio.run(
        list_pending_notification_delivery_models(
            session,  # type: ignore[arg-type]
            limit=10,
        )
    )

    assert response == [delivery]


def test_process_notification_delivery_posts_webhook_and_marks_sent() -> None:
    delivery = build_delivery()
    http_client = FakeHttpClient(FakeHttpResponse(204))

    result = asyncio.run(process_notification_delivery(delivery, http_client=http_client))

    assert result.delivery_id == delivery.id
    assert result.channel == "webhook"
    assert result.status == NotificationDeliveryStatus.SENT
    assert result.error is None
    assert delivery.status == NotificationDeliveryStatus.SENT.value
    assert delivery.sent_at is not None
    assert delivery.attempts == 0
    assert http_client.posts[0]["url"] == "https://example.test/verigraph-webhook"
    payload = http_client.posts[0]["json"]
    assert payload["delivery_id"] == str(delivery.id)
    assert payload["notification_id"] == str(delivery.notification_id)
    assert payload["event_type"] == "case.critical"


def test_process_notification_delivery_marks_webhook_without_destination_as_failed() -> None:
    delivery = build_delivery()
    delivery.destination = None

    result = asyncio.run(process_notification_delivery(delivery))

    assert result.status == NotificationDeliveryStatus.FAILED
    assert result.error == "Webhook destination URL is missing."
    assert delivery.status == NotificationDeliveryStatus.FAILED.value
    assert delivery.attempts == 1
    assert delivery.last_error == "Webhook destination URL is missing."


def test_process_notification_delivery_marks_webhook_http_error_as_failed() -> None:
    delivery = build_delivery()
    http_client = FakeHttpClient(FakeHttpResponse(500, "server error"))

    result = asyncio.run(process_notification_delivery(delivery, http_client=http_client))

    assert result.status == NotificationDeliveryStatus.PENDING
    assert result.error == "Webhook returned HTTP 500: server error"
    assert delivery.status == NotificationDeliveryStatus.PENDING.value
    assert delivery.attempts == 1
    assert delivery.last_error == "Webhook returned HTTP 500: server error"
    assert delivery.next_attempt_at is not None


def test_process_notification_delivery_marks_invalid_channel_as_failed() -> None:
    delivery = build_delivery(channel="pagerduty")

    result = asyncio.run(process_notification_delivery(delivery))

    assert result.status == NotificationDeliveryStatus.FAILED
    assert result.error
    assert delivery.status == NotificationDeliveryStatus.FAILED.value
    assert delivery.attempts == 1
    assert delivery.last_error
    assert delivery.next_attempt_at is None


def test_dispatch_notification_delivery_supports_webhook_and_slack_channels() -> None:
    http_client = FakeHttpClient(FakeHttpResponse(200))
    for channel in (NotificationDeliveryChannel.WEBHOOK, NotificationDeliveryChannel.SLACK):
        delivery = build_delivery(channel=channel.value)

        result = asyncio.run(dispatch_notification_delivery(delivery, http_client=http_client))

        assert result.success is True
        assert result.error is None


def test_dispatch_notification_delivery_fails_email_without_smtp_host(monkeypatch) -> None:
    monkeypatch.setattr("app.services.delivery_worker.settings.smtp_host", "")
    delivery = build_delivery(channel=NotificationDeliveryChannel.EMAIL.value)

    result = asyncio.run(dispatch_notification_delivery(delivery))

    assert result.success is False
    assert result.retryable is False
    assert result.error == "SMTP host is missing."


def test_process_pending_notification_deliveries_commits_when_batch_exists() -> None:
    sent_delivery = build_delivery()
    failed_delivery = build_delivery(channel="pagerduty")
    session = FakeWorkerSession([FakeScalarManyResult([sent_delivery, failed_delivery])])

    result = asyncio.run(
        process_pending_notification_deliveries(
            session,  # type: ignore[arg-type]
            limit=50,
            http_client=FakeHttpClient(FakeHttpResponse(200)),
        )
    )

    assert session.committed is True
    assert result.processed == 2
    assert result.sent == 1
    assert result.scheduled == 0
    assert result.failed == 1
    assert sent_delivery.status == NotificationDeliveryStatus.SENT.value
    assert failed_delivery.status == NotificationDeliveryStatus.FAILED.value


def test_process_pending_notification_deliveries_leaves_retryable_webhook_for_later() -> None:
    retry_delivery = build_delivery()
    session = FakeWorkerSession([FakeScalarManyResult([retry_delivery])])

    result = asyncio.run(
        process_pending_notification_deliveries(
            session,  # type: ignore[arg-type]
            limit=50,
            http_client=FakeHttpClient(FakeHttpResponse(500, "server error")),
        )
    )

    assert session.committed is True
    assert result.processed == 1
    assert result.sent == 0
    assert result.scheduled == 1
    assert result.failed == 0
    assert retry_delivery.status == NotificationDeliveryStatus.PENDING.value
    assert retry_delivery.attempts == 1
    assert retry_delivery.next_attempt_at is not None


def test_process_pending_notification_deliveries_does_not_commit_empty_batch() -> None:
    session = FakeWorkerSession([FakeScalarManyResult([])])

    result = asyncio.run(
        process_pending_notification_deliveries(
            session,  # type: ignore[arg-type]
        )
    )

    assert session.committed is False
    assert result.processed == 0
    assert result.sent == 0
    assert result.failed == 0


def test_build_delivery_worker_run_result_counts_statuses() -> None:
    sent_delivery = build_delivery()
    failed_delivery = build_delivery(channel="pagerduty")
    sent = asyncio.run(process_notification_delivery(sent_delivery, http_client=FakeHttpClient(FakeHttpResponse(200))))
    failed = asyncio.run(process_notification_delivery(failed_delivery))

    result = build_delivery_worker_run_result([sent, failed])

    assert result.processed == 2
    assert result.sent == 1
    assert result.scheduled == 0
    assert result.failed == 1


def test_process_notification_delivery_fails_finally_after_max_attempts() -> None:
    delivery = build_delivery()
    delivery.attempts = 2
    http_client = FakeHttpClient(FakeHttpResponse(500, "server error"))

    result = asyncio.run(process_notification_delivery(delivery, http_client=http_client))

    assert result.status == NotificationDeliveryStatus.FAILED
    assert delivery.status == NotificationDeliveryStatus.FAILED.value
    assert delivery.attempts == 3
    assert delivery.next_attempt_at is None


def test_process_notification_deliveries_parse_args_reads_limit() -> None:
    args = parse_args(["--limit", "25"])

    assert args.limit == 25


def test_build_webhook_payload_uses_notification_metadata() -> None:
    delivery = build_delivery()

    payload = build_webhook_payload(delivery)

    assert payload["delivery_id"] == str(delivery.id)
    assert payload["notification_id"] == str(delivery.notification_id)
    assert payload["channel"] == "webhook"
    assert payload["event_type"] == "case.critical"
    assert payload["severity"] == "critical"
    assert payload["title"] == "Expediente critico detectado"
    assert payload["message"] == "El expediente quedo en nivel critical."
    assert payload["attempt"] == 1


def test_build_slack_payload_wraps_webhook_payload() -> None:
    delivery = build_delivery(channel=NotificationDeliveryChannel.SLACK.value)

    payload = build_slack_payload(delivery)

    assert payload["text"] == "[CRITICAL] Expediente critico detectado"
    assert payload["verigraph"]["event_type"] == "case.critical"


def test_build_email_message_uses_delivery_destination() -> None:
    delivery = build_delivery(channel=NotificationDeliveryChannel.EMAIL.value)

    message = build_email_message(delivery)

    assert message["To"] == "alerts@example.test"
    assert message["Subject"] == "Expediente critico detectado"
