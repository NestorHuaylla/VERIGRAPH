from typing import Any

from worker.services.alerts import build_email_message, send_alert


class FakeHttpResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeHttpClient:
    def __init__(self, response: FakeHttpResponse) -> None:
        self.response = response
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any]) -> FakeHttpResponse:
        self.posts.append({"url": url, "json": json})
        return self.response


def test_send_alert_skips_unconfigured_webhook(monkeypatch: Any) -> None:
    monkeypatch.setattr("worker.services.alerts.settings.notification_webhook_url", "")

    result = send_alert("webhook", "Alerta", "Detalle")

    assert result["status"] == "skipped"
    assert result["retryable"] is False


def test_send_alert_posts_webhook_payload(monkeypatch: Any) -> None:
    monkeypatch.setattr("worker.services.alerts.settings.notification_webhook_url", "https://example.test/hook")
    http_client = FakeHttpClient(FakeHttpResponse(204))

    result = send_alert("webhook", "Alerta", "Detalle", http_client=http_client)

    assert result == {"channel": "webhook", "status": "sent", "retryable": False}
    assert http_client.posts[0]["url"] == "https://example.test/hook"
    assert http_client.posts[0]["json"]["title"] == "Alerta"


def test_send_alert_posts_slack_payload(monkeypatch: Any) -> None:
    monkeypatch.setattr("worker.services.alerts.settings.slack_webhook_url", "https://hooks.slack.test/hook")
    http_client = FakeHttpClient(FakeHttpResponse(200))

    result = send_alert("slack", "Alerta", "Detalle", http_client=http_client)

    assert result["status"] == "sent"
    assert http_client.posts[0]["json"]["blocks"][0]["text"]["text"] == "*Alerta*\nDetalle"


def test_send_alert_marks_http_failure_retryable(monkeypatch: Any) -> None:
    monkeypatch.setattr("worker.services.alerts.settings.notification_webhook_url", "https://example.test/hook")
    http_client = FakeHttpClient(FakeHttpResponse(500, "server error"))

    result = send_alert("webhook", "Alerta", "Detalle", http_client=http_client)

    assert result["status"] == "failed"
    assert result["retryable"] is True
    assert result["error"] == "HTTP 500: server error"


def test_build_email_message_uses_configured_destination(monkeypatch: Any) -> None:
    monkeypatch.setattr("worker.services.alerts.settings.alert_email_to", "alerts@example.test")
    monkeypatch.setattr("worker.services.alerts.settings.alert_email_from", "from@example.test")

    message = build_email_message("Alerta", "Detalle")

    assert message["To"] == "alerts@example.test"
    assert message["From"] == "from@example.test"
    assert message["Subject"] == "Alerta"
