from __future__ import annotations

import re
import string
from dataclasses import dataclass

from fastapi import Request

from app.schemas.report import ReportCreate


MAX_LINKS_IN_REASON = 5
MAX_SYMBOL_RATIO = 0.35
MIN_REPETITIVE_WORD_COUNT = 20
MIN_UNIQUE_WORD_RATIO = 0.2
MAX_USER_AGENT_LENGTH = 500

URL_PATTERN = re.compile(r"https?://|www\.|[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


@dataclass(frozen=True)
class AbuseSignal:
    code: str
    message: str


class AbuseValidationError(Exception):
    def __init__(self, signal: AbuseSignal) -> None:
        super().__init__(signal.message)
        self.signal = signal


def validate_public_report(payload: ReportCreate) -> None:
    signals = collect_public_report_abuse_signals(payload)
    if signals:
        raise AbuseValidationError(signals[0])


def collect_public_report_abuse_signals(payload: ReportCreate) -> list[AbuseSignal]:
    reason = payload.reason.strip()
    signals: list[AbuseSignal] = []

    if has_too_many_links(reason):
        signals.append(
            AbuseSignal(
                code="too_many_links",
                message="El reporte contiene demasiados enlaces.",
            )
        )
    if is_too_repetitive(reason):
        signals.append(
            AbuseSignal(
                code="repetitive_text",
                message="El reporte parece demasiado repetitivo.",
            )
        )
    if has_too_many_symbols(reason):
        signals.append(
            AbuseSignal(
                code="too_many_symbols",
                message="El reporte contiene demasiados caracteres no textuales.",
            )
        )

    return signals


def has_too_many_links(text: str) -> bool:
    return len(URL_PATTERN.findall(text)) > MAX_LINKS_IN_REASON


def is_too_repetitive(text: str) -> bool:
    words = [word.lower() for word in WORD_PATTERN.findall(text)]
    if len(words) < MIN_REPETITIVE_WORD_COUNT:
        return False

    unique_ratio = len(set(words)) / len(words)
    return unique_ratio < MIN_UNIQUE_WORD_RATIO


def has_too_many_symbols(text: str) -> bool:
    if not text:
        return False

    meaningful_chars = [char for char in text if not char.isspace()]
    if not meaningful_chars:
        return False

    symbol_count = sum(1 for char in meaningful_chars if not char.isalnum() and char not in string.punctuation + ".,;:!?¿¡/@+-_#")
    return symbol_count / len(meaningful_chars) > MAX_SYMBOL_RATIO


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",", maxsplit=1)[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    if not user_agent:
        return None
    return user_agent[:MAX_USER_AGENT_LENGTH]


def build_public_report_request_metadata(request: Request, *, source: str = "public_form") -> dict:
    return {
        "anti_abuse": {
            "client_ip": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "source": source,
        }
    }
