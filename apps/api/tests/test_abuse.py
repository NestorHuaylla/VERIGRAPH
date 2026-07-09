from types import SimpleNamespace

import pytest

from app.core.constants import EntityType
from app.schemas.report import ReportCreate
from app.services.abuse import (
    AbuseValidationError,
    build_public_report_request_metadata,
    collect_public_report_abuse_signals,
    get_client_ip,
    get_user_agent,
    validate_public_report,
)


class FakeRequest:
    def __init__(self, *, headers: dict[str, str] | None = None, client_host: str | None = "127.0.0.1") -> None:
        self.headers = headers or {}
        self.client = SimpleNamespace(host=client_host) if client_host else None


def build_payload(reason: str) -> ReportCreate:
    return ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason=reason,
    )


def test_validate_public_report_allows_normal_reason() -> None:
    payload = build_payload("Promete ganancia garantizada y pide deposito primero por WhatsApp.")

    validate_public_report(payload)


def test_collect_public_report_abuse_signals_detects_too_many_links() -> None:
    payload = build_payload(
        "Revisar estos enlaces "
        "https://a.test https://b.test https://c.test https://d.test https://e.test https://f.test"
    )

    signals = collect_public_report_abuse_signals(payload)

    assert signals[0].code == "too_many_links"


def test_validate_public_report_rejects_repetitive_text() -> None:
    payload = build_payload("fraude " * 30)

    with pytest.raises(AbuseValidationError) as exc_info:
        validate_public_report(payload)

    assert exc_info.value.signal.code == "repetitive_text"


def test_validate_public_report_rejects_symbol_noise() -> None:
    payload = build_payload("⚠" * 40 + " estafa")

    with pytest.raises(AbuseValidationError) as exc_info:
        validate_public_report(payload)

    assert exc_info.value.signal.code == "too_many_symbols"


def test_get_client_ip_prefers_x_forwarded_for() -> None:
    request = FakeRequest(headers={"x-forwarded-for": "203.0.113.10, 10.0.0.2"}, client_host="127.0.0.1")

    assert get_client_ip(request) == "203.0.113.10"  # type: ignore[arg-type]


def test_get_client_ip_uses_x_real_ip_before_socket_client() -> None:
    request = FakeRequest(headers={"x-real-ip": "203.0.113.20"}, client_host="127.0.0.1")

    assert get_client_ip(request) == "203.0.113.20"  # type: ignore[arg-type]


def test_get_client_ip_ignores_forwarded_headers_from_untrusted_socket() -> None:
    # Un cliente que no llega a traves de un proxy confiable no debe poder
    # falsificar su IP mandando X-Forwarded-For / X-Real-IP el mismo.
    request = FakeRequest(
        headers={"x-forwarded-for": "203.0.113.10", "x-real-ip": "203.0.113.20"},
        client_host="198.51.100.5",
    )

    assert get_client_ip(request) == "198.51.100.5"  # type: ignore[arg-type]


def test_build_public_report_request_metadata_includes_ip_user_agent_and_source() -> None:
    request = FakeRequest(
        headers={
            "x-forwarded-for": "203.0.113.30",
            "user-agent": "pytest-browser",
        }
    )

    metadata = build_public_report_request_metadata(request)  # type: ignore[arg-type]

    assert metadata == {
        "anti_abuse": {
            "client_ip": "203.0.113.30",
            "user_agent": "pytest-browser",
            "source": "public_form",
        }
    }


def test_get_user_agent_truncates_long_value() -> None:
    request = FakeRequest(headers={"user-agent": "a" * 600})

    assert len(get_user_agent(request)) == 500  # type: ignore[arg-type]
