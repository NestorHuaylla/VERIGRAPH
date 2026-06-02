from __future__ import annotations

from email.message import EmailMessage
import smtplib
from typing import Any, Protocol

import httpx

from worker.config import settings


ALERT_TIMEOUT_SECONDS = 10.0


class AlertHttpClient(Protocol):
    def post(self, url: str, *, json: dict[str, Any]) -> Any:
        pass


def send_alert(
    channel: str,
    title: str,
    message: str,
    *,
    http_client: AlertHttpClient | None = None,
) -> dict[str, Any]:
    normalized_channel = channel.strip().lower()
    if normalized_channel == "webhook":
        return send_webhook_alert(title, message, http_client=http_client)
    if normalized_channel == "slack":
        return send_slack_alert(title, message, http_client=http_client)
    if normalized_channel == "email":
        return send_email_alert(title, message)
    return {
        "channel": normalized_channel,
        "status": "failed",
        "retryable": False,
        "error": f"Unsupported alert channel: {channel}",
    }


def send_webhook_alert(
    title: str,
    message: str,
    *,
    http_client: AlertHttpClient | None = None,
) -> dict[str, Any]:
    if not settings.notification_webhook_url:
        return missing_destination("webhook", "NOTIFICATION_WEBHOOK_URL is not configured.")
    payload = build_webhook_payload(title, message)
    return post_alert_payload("webhook", settings.notification_webhook_url, payload, http_client=http_client)


def send_slack_alert(
    title: str,
    message: str,
    *,
    http_client: AlertHttpClient | None = None,
) -> dict[str, Any]:
    if not settings.slack_webhook_url:
        return missing_destination("slack", "SLACK_WEBHOOK_URL is not configured.")
    payload = build_slack_payload(title, message)
    return post_alert_payload("slack", settings.slack_webhook_url, payload, http_client=http_client)


def post_alert_payload(
    channel: str,
    url: str,
    payload: dict[str, Any],
    *,
    http_client: AlertHttpClient | None = None,
) -> dict[str, Any]:
    try:
        if http_client is not None:
            response = http_client.post(url, json=payload)
        else:
            with httpx.Client(timeout=ALERT_TIMEOUT_SECONDS) as client:
                response = client.post(url, json=payload)
    except httpx.HTTPError as exc:
        return {"channel": channel, "status": "failed", "retryable": True, "error": str(exc)}

    status_code = int(getattr(response, "status_code", 0) or 0)
    if 200 <= status_code < 300:
        return {"channel": channel, "status": "sent", "retryable": False}

    response_text = str(getattr(response, "text", ""))[:500]
    detail = f": {response_text}" if response_text else ""
    return {
        "channel": channel,
        "status": "failed",
        "retryable": True,
        "error": f"HTTP {status_code}{detail}",
    }


def send_email_alert(title: str, message: str) -> dict[str, Any]:
    if not settings.alert_email_to:
        return missing_destination("email", "ALERT_EMAIL_TO is not configured.")
    if not settings.smtp_host:
        return missing_destination("email", "SMTP_HOST is not configured.")

    try:
        email_message = build_email_message(title, message)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=ALERT_TIMEOUT_SECONDS) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(email_message)
    except (OSError, smtplib.SMTPException) as exc:
        return {"channel": "email", "status": "failed", "retryable": True, "error": str(exc)}

    return {"channel": "email", "status": "sent", "retryable": False}


def build_webhook_payload(title: str, message: str) -> dict[str, Any]:
    return {
        "event_type": "risk.alert",
        "title": title,
        "message": message,
        "source": "worker-alerts",
    }


def build_slack_payload(title: str, message: str) -> dict[str, Any]:
    return {
        "text": title,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n{message}",
                },
            }
        ],
    }


def build_email_message(title: str, message: str) -> EmailMessage:
    email_message = EmailMessage()
    email_message["Subject"] = title
    email_message["From"] = settings.alert_email_from
    email_message["To"] = settings.alert_email_to
    email_message.set_content(message)
    return email_message


def missing_destination(channel: str, error: str) -> dict[str, Any]:
    return {
        "channel": channel,
        "status": "skipped",
        "retryable": False,
        "error": error,
    }
