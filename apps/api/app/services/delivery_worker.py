import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import NotificationDeliveryChannel, NotificationDeliveryStatus
from app.models.notification import NotificationDelivery
from app.schemas.notification_delivery import NotificationDeliveryStatusUpdate
from app.services.notification_deliveries import apply_notification_delivery_status_update, apply_notification_delivery_retry_schedule


DEFAULT_DELIVERY_BATCH_LIMIT = 50
WEBHOOK_TIMEOUT_SECONDS = 5.0


class WebhookHttpClient(Protocol):
    async def post(self, url: str, *, json: dict[str, Any]) -> Any:
        pass


@dataclass(frozen=True)
class DeliveryHandlerResult:
    success: bool
    error: str | None = None
    retryable: bool = True


@dataclass(frozen=True)
class DeliveryProcessResult:
    delivery_id: UUID
    channel: str
    status: NotificationDeliveryStatus
    error: str | None = None


@dataclass(frozen=True)
class DeliveryWorkerRunResult:
    processed: int
    sent: int
    scheduled: int
    failed: int
    results: list[DeliveryProcessResult] = field(default_factory=list)


async def process_pending_notification_deliveries(
    db: AsyncSession,
    *,
    limit: int = DEFAULT_DELIVERY_BATCH_LIMIT,
    http_client: WebhookHttpClient | None = None,
) -> DeliveryWorkerRunResult:
    deliveries = await list_pending_notification_delivery_models(db, limit=limit)
    results: list[DeliveryProcessResult] = []

    for delivery in deliveries:
        results.append(await process_notification_delivery(delivery, http_client=http_client))

    if deliveries:
        await db.commit()

    return build_delivery_worker_run_result(results)


async def list_pending_notification_delivery_models(
    db: AsyncSession,
    *,
    limit: int = DEFAULT_DELIVERY_BATCH_LIMIT,
) -> list[NotificationDelivery]:
    result = await db.execute(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.status == NotificationDeliveryStatus.PENDING.value,
            or_(
                NotificationDelivery.next_attempt_at.is_(None),
                NotificationDelivery.next_attempt_at <= datetime.now(timezone.utc),
            ),
        )
        .order_by(NotificationDelivery.next_attempt_at.asc().nullsfirst(), NotificationDelivery.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def process_notification_delivery(
    delivery: NotificationDelivery,
    *,
    http_client: WebhookHttpClient | None = None,
) -> DeliveryProcessResult:
    try:
        handler_result = await dispatch_notification_delivery(delivery, http_client=http_client)
    except Exception as exc:
        handler_result = DeliveryHandlerResult(success=False, error=str(exc))

    if handler_result.success:
        apply_notification_delivery_status_update(
            delivery,
            NotificationDeliveryStatusUpdate(status=NotificationDeliveryStatus.SENT),
        )
        return DeliveryProcessResult(
            delivery_id=delivery.id,
            channel=delivery.channel,
            status=NotificationDeliveryStatus.SENT,
            error=None,
        )

    error = handler_result.error or "Delivery handler failed without error detail."
    if handler_result.retryable:
        apply_notification_delivery_retry_schedule(delivery, error=error)
    else:
        apply_notification_delivery_status_update(
            delivery,
            NotificationDeliveryStatusUpdate(status=NotificationDeliveryStatus.FAILED, error=error),
        )
    return DeliveryProcessResult(
        delivery_id=delivery.id,
        channel=delivery.channel,
        status=NotificationDeliveryStatus(delivery.status),
        error=error,
    )


async def dispatch_notification_delivery(
    delivery: NotificationDelivery,
    *,
    http_client: WebhookHttpClient | None = None,
) -> DeliveryHandlerResult:
    try:
        channel = NotificationDeliveryChannel(delivery.channel)
    except ValueError:
        return DeliveryHandlerResult(success=False, error=f"Unsupported delivery channel: {delivery.channel}", retryable=False)

    if channel == NotificationDeliveryChannel.WEBHOOK:
        return await deliver_webhook(delivery, http_client=http_client)
    if channel == NotificationDeliveryChannel.EMAIL:
        return await deliver_email(delivery)
    if channel == NotificationDeliveryChannel.SLACK:
        return await deliver_slack(delivery, http_client=http_client)
    return DeliveryHandlerResult(success=False, error=f"Unsupported delivery channel: {delivery.channel}", retryable=False)


async def deliver_webhook(
    delivery: NotificationDelivery,
    *,
    http_client: WebhookHttpClient | None = None,
) -> DeliveryHandlerResult:
    if not delivery.destination:
        return DeliveryHandlerResult(success=False, error="Webhook destination URL is missing.", retryable=False)

    payload = build_webhook_payload(delivery)
    if http_client is not None:
        return await post_webhook_payload(http_client, delivery.destination, payload)

    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
        return await post_webhook_payload(client, delivery.destination, payload)


async def post_webhook_payload(
    http_client: WebhookHttpClient,
    url: str,
    payload: dict[str, Any],
) -> DeliveryHandlerResult:
    try:
        response = await http_client.post(url, json=payload)
    except httpx.HTTPError as exc:
        return DeliveryHandlerResult(success=False, error=f"Webhook request failed: {exc}", retryable=True)

    status_code = int(getattr(response, "status_code", 0) or 0)
    if 200 <= status_code < 300:
        return DeliveryHandlerResult(success=True)

    response_text = str(getattr(response, "text", ""))[:500]
    detail = f": {response_text}" if response_text else ""
    return DeliveryHandlerResult(success=False, error=f"Webhook returned HTTP {status_code}{detail}", retryable=True)


async def deliver_slack(
    delivery: NotificationDelivery,
    *,
    http_client: WebhookHttpClient | None = None,
) -> DeliveryHandlerResult:
    destination = delivery.destination or settings.slack_webhook_url
    if not destination:
        return DeliveryHandlerResult(success=False, error="Slack webhook URL is missing.", retryable=False)

    payload = build_slack_payload(delivery)
    if http_client is not None:
        return await post_webhook_payload(http_client, destination, payload)

    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
        return await post_webhook_payload(client, destination, payload)


async def deliver_email(delivery: NotificationDelivery) -> DeliveryHandlerResult:
    if not delivery.destination:
        return DeliveryHandlerResult(success=False, error="Email destination is missing.", retryable=False)
    if not settings.smtp_host:
        return DeliveryHandlerResult(success=False, error="SMTP host is missing.", retryable=False)

    try:
        await asyncio.to_thread(send_email_delivery, delivery)
    except OSError as exc:
        return DeliveryHandlerResult(success=False, error=f"SMTP request failed: {exc}", retryable=True)
    except smtplib.SMTPException as exc:
        return DeliveryHandlerResult(success=False, error=f"SMTP request failed: {exc}", retryable=True)

    return DeliveryHandlerResult(success=True)


def send_email_delivery(delivery: NotificationDelivery) -> None:
    message = build_email_message(delivery)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=WEBHOOK_TIMEOUT_SECONDS) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def build_webhook_payload(delivery: NotificationDelivery) -> dict[str, Any]:
    metadata = delivery.metadata_json or {}
    return {
        "delivery_id": str(delivery.id),
        "notification_id": str(delivery.notification_id),
        "channel": delivery.channel,
        "event_type": metadata.get("notification_event_type"),
        "severity": metadata.get("notification_severity"),
        "title": metadata.get("notification_title"),
        "message": metadata.get("notification_message"),
        "metadata": metadata.get("notification_metadata") or {},
        "delivery_metadata": metadata,
        "attempt": delivery.attempts + 1,
    }


def build_slack_payload(delivery: NotificationDelivery) -> dict[str, Any]:
    webhook_payload = build_webhook_payload(delivery)
    severity = str(webhook_payload.get("severity") or "info").upper()
    title = webhook_payload.get("title") or "VERIGRAPH alert"
    message = webhook_payload.get("message") or ""
    return {
        "text": f"[{severity}] {title}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*[{severity}] {title}*\n{message}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"event={webhook_payload.get('event_type')} delivery={webhook_payload.get('delivery_id')}",
                    }
                ],
            },
        ],
        "verigraph": webhook_payload,
    }


def build_email_message(delivery: NotificationDelivery) -> EmailMessage:
    payload = build_webhook_payload(delivery)
    recipients = [email.strip() for email in str(delivery.destination or "").split(",") if email.strip()]
    message = EmailMessage()
    message["Subject"] = str(payload.get("title") or "VERIGRAPH alert")
    message["From"] = settings.alert_email_from
    message["To"] = ", ".join(recipients)
    message.set_content(
        "\n".join(
            [
                str(payload.get("message") or ""),
                "",
                f"Event: {payload.get('event_type')}",
                f"Severity: {payload.get('severity')}",
                f"Notification: {payload.get('notification_id')}",
                f"Delivery: {payload.get('delivery_id')}",
            ]
        )
    )
    return message


def build_delivery_worker_run_result(results: list[DeliveryProcessResult]) -> DeliveryWorkerRunResult:
    sent = sum(1 for result in results if result.status == NotificationDeliveryStatus.SENT)
    scheduled = sum(1 for result in results if result.status == NotificationDeliveryStatus.PENDING)
    failed = sum(1 for result in results if result.status == NotificationDeliveryStatus.FAILED)
    return DeliveryWorkerRunResult(
        processed=len(results),
        sent=sent,
        scheduled=scheduled,
        failed=failed,
        results=results,
    )
