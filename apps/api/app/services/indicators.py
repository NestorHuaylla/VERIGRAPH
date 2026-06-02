import re
from dataclasses import dataclass

from app.core.constants import EntityType
from app.services.normalizer import (
    BTC_BECH32_RE,
    BTC_LEGACY_RE,
    EVM_WALLET_RE,
    TRON_WALLET_RE,
    normalize_entity,
)

URL_LIKE_RE = re.compile(r"\b(?:https?://)?(?:wa\.me|t\.me|telegram\.me)/[^\s<>'\"]+", re.IGNORECASE)
HTTP_URL_RE = re.compile(r"\bhttps?://[^\s<>'\"]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().\-]{7,}\d(?!\w)")
TELEGRAM_HANDLE_RE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{3,64}\b")
DOMAIN_RE = re.compile(r"(?<!@)\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/[^\s<>'\"]*)?")


@dataclass(frozen=True)
class ExtractedIndicator:
    entity_type: EntityType
    raw_value: str
    source: str = "report_reason"


def extract_indicators(text: str) -> list[ExtractedIndicator]:
    indicators: list[ExtractedIndicator] = []
    occupied_spans: list[tuple[int, int]] = []

    for match in HTTP_URL_RE.finditer(text):
        add_url_like_indicator(indicators, occupied_spans, match.group(0), match.span())

    for match in URL_LIKE_RE.finditer(text):
        if span_overlaps(match.span(), occupied_spans):
            continue
        add_url_like_indicator(indicators, occupied_spans, match.group(0), match.span())

    for pattern in [EVM_WALLET_RE, BTC_BECH32_RE, BTC_LEGACY_RE, TRON_WALLET_RE]:
        for match in pattern.finditer(text):
            add_indicator(indicators, occupied_spans, EntityType.WALLET, match.group(0), match.span())

    for match in EMAIL_RE.finditer(text):
        add_indicator(indicators, occupied_spans, EntityType.EMAIL, match.group(0), match.span())

    for match in PHONE_RE.finditer(text):
        if span_overlaps(match.span(), occupied_spans):
            continue
        add_indicator(indicators, occupied_spans, EntityType.PHONE, match.group(0), match.span())

    for match in TELEGRAM_HANDLE_RE.finditer(text):
        if span_overlaps(match.span(), occupied_spans):
            continue
        add_indicator(indicators, occupied_spans, EntityType.SOCIAL_CHANNEL, match.group(0), match.span())

    for match in DOMAIN_RE.finditer(text):
        if span_overlaps(match.span(), occupied_spans):
            continue
        add_indicator(indicators, occupied_spans, EntityType.DOMAIN, match.group(0), match.span())

    return dedupe_indicators(indicators)


def add_url_like_indicator(
    indicators: list[ExtractedIndicator],
    occupied_spans: list[tuple[int, int]],
    raw_value: str,
    span: tuple[int, int],
) -> None:
    lowered = raw_value.lower()
    if "wa.me/" in lowered:
        add_indicator(indicators, occupied_spans, EntityType.PHONE, raw_value, span)
        return
    if "t.me/" in lowered or "telegram.me/" in lowered:
        add_indicator(indicators, occupied_spans, EntityType.SOCIAL_CHANNEL, raw_value, span)
        return
    add_indicator(indicators, occupied_spans, EntityType.URL, raw_value, span)


def add_indicator(
    indicators: list[ExtractedIndicator],
    occupied_spans: list[tuple[int, int]],
    entity_type: EntityType,
    raw_value: str,
    span: tuple[int, int],
) -> None:
    cleaned = clean_indicator_value(raw_value)
    if not cleaned:
        return
    indicators.append(ExtractedIndicator(entity_type=entity_type, raw_value=cleaned))
    occupied_spans.append(span)


def clean_indicator_value(value: str) -> str:
    return value.strip().strip(".,;:)]}>'\"")


def span_overlaps(span: tuple[int, int], occupied_spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied_spans)


def dedupe_indicators(indicators: list[ExtractedIndicator]) -> list[ExtractedIndicator]:
    seen: set[tuple[EntityType, str]] = set()
    deduped: list[ExtractedIndicator] = []

    for indicator in indicators:
        normalized = normalize_entity(indicator.entity_type, indicator.raw_value)
        key = (indicator.entity_type, normalized.value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(indicator)

    return deduped
