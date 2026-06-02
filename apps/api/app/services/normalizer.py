import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse, urlunparse

from app.core.constants import EntityType

TELEGRAM_HOSTS = {"t.me", "telegram.me"}
EVM_WALLET_RE = re.compile(r"0x[a-fA-F0-9]{40}")
BTC_BECH32_RE = re.compile(r"bc1[ac-hj-np-z02-9]{11,71}", re.IGNORECASE)
BTC_LEGACY_RE = re.compile(r"[13][a-km-zA-HJ-NP-Z1-9]{25,34}")
TRON_WALLET_RE = re.compile(r"T[1-9A-HJ-NP-Za-km-z]{33}")


@dataclass(frozen=True)
class NormalizedEntity:
    type: EntityType
    value: str
    display_value: str


def extract_phone_candidate(value: str) -> str | None:
    raw = value.strip()
    candidate = raw.lower()

    if "wa.me/" in candidate or "whatsapp.com/send" in candidate:
        parsed = urlparse(raw if raw.startswith(("http://", "https://")) else f"https://{raw}")

        if "wa.me" in parsed.netloc:
            phone = parsed.path.strip("/").split("/")[0]
            return phone or None

        query = parse_qs(parsed.query)
        phone_values = query.get("phone")
        if phone_values:
            return phone_values[0]

    if re.fullmatch(r"\+?[0-9\s\-()]{7,20}", raw):
        return raw

    return None


def normalize_phone(value: str, default_country_code: str = "51") -> str:
    candidate = extract_phone_candidate(value) or value
    digits = re.sub(r"\D", "", candidate)

    if not digits:
        return value.strip()

    if candidate.strip().startswith("+"):
        return f"+{digits}"

    if digits.startswith(default_country_code) and len(digits) > 9:
        return f"+{digits}"

    if len(digits) == 9:
        return f"+{default_country_code}{digits}"

    return f"+{digits}"


def ensure_url_scheme(value: str) -> str:
    raw = value.strip()
    if raw.startswith(("http://", "https://")):
        return raw
    return f"https://{raw}"


def strip_www(hostname: str) -> str:
    hostname = hostname.strip().lower()
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def normalize_domain(value: str) -> str:
    parsed = urlparse(ensure_url_scheme(value))
    hostname = strip_www(parsed.hostname or value.strip())
    return hostname.rstrip(".")


def normalize_url(value: str) -> str:
    parsed = urlparse(ensure_url_scheme(value))
    scheme = parsed.scheme.lower() or "https"
    hostname = normalize_domain(value)
    path = parsed.path.rstrip("/")
    normalized = urlunparse((scheme, hostname, path, "", "", ""))
    return normalized.rstrip("/")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def extract_telegram_handle(value: str) -> str | None:
    raw = value.strip()
    candidate = raw.lower()

    if candidate.startswith("@") and "." not in candidate and " " not in candidate:
        handle = raw[1:]
        return handle if re.fullmatch(r"[A-Za-z0-9_]{3,64}", handle) else None

    parsed = urlparse(ensure_url_scheme(raw))
    hostname = strip_www(parsed.hostname or "")
    if hostname not in TELEGRAM_HOSTS:
        return None

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if not parts:
        return None

    handle = parts[1] if len(parts) >= 2 and parts[0].lower() == "s" else parts[0]
    return handle if re.fullmatch(r"[A-Za-z0-9_]{3,64}", handle) else None


def normalize_social_handle(value: str) -> str:
    telegram_handle = extract_telegram_handle(value)
    if telegram_handle:
        return f"telegram:{telegram_handle.lower()}"

    return value.strip().lower()


def compact_wallet_value(value: str) -> str:
    compact = re.sub(r"\s+", "", value.strip())
    return re.sub(
        r"^(wallet|address|addr|direccion|usdt|btc|bitcoin|eth|ethereum|evm|tron|trx)[:=\-]+",
        "",
        compact,
        flags=re.IGNORECASE,
    )


def detect_wallet_network(value: str) -> tuple[str, str] | None:
    compact = compact_wallet_value(value)

    if EVM_WALLET_RE.fullmatch(compact):
        return ("evm", compact.lower())

    if BTC_BECH32_RE.fullmatch(compact):
        return ("btc", compact.lower())

    if BTC_LEGACY_RE.fullmatch(compact):
        return ("btc", compact)

    if TRON_WALLET_RE.fullmatch(compact):
        return ("trx", compact)

    return None


def normalize_wallet(value: str) -> str:
    detected = detect_wallet_network(value)
    if detected:
        network, address = detected
        return f"{network}:{address}"

    compact = compact_wallet_value(value)
    return f"wallet:{compact.lower()}"


def infer_entity_type(value: str) -> EntityType:
    candidate = value.strip().lower()

    if extract_phone_candidate(value):
        return EntityType.PHONE
    if extract_telegram_handle(value):
        return EntityType.SOCIAL_CHANNEL
    if detect_wallet_network(value):
        return EntityType.WALLET
    if candidate.startswith(("http://", "https://")):
        return EntityType.URL
    if "@" in candidate and "." in candidate:
        return EntityType.EMAIL
    if re.fullmatch(r"\+?[0-9\s\-()]{7,20}", candidate):
        return EntityType.PHONE
    if "." in candidate and " " not in candidate:
        return EntityType.DOMAIN
    return EntityType.OTHER


def normalize_entity(entity_type: EntityType, value: str) -> NormalizedEntity:
    raw = value.strip()

    if entity_type == EntityType.URL:
        normalized = normalize_url(raw)
        return NormalizedEntity(entity_type, normalized, normalized)

    if entity_type == EntityType.DOMAIN:
        domain = normalize_domain(raw)
        return NormalizedEntity(entity_type, domain, domain)

    if entity_type == EntityType.PHONE:
        phone = normalize_phone(raw)
        return NormalizedEntity(entity_type, phone, phone)

    if entity_type == EntityType.EMAIL:
        email = normalize_email(raw)
        return NormalizedEntity(entity_type, email, email)

    if entity_type in {EntityType.SOCIAL_PROFILE, EntityType.SOCIAL_CHANNEL}:
        handle = normalize_social_handle(raw)
        return NormalizedEntity(entity_type, handle, handle)

    if entity_type == EntityType.WALLET:
        wallet = normalize_wallet(raw)
        return NormalizedEntity(entity_type, wallet, wallet)

    return NormalizedEntity(entity_type, raw.lower(), raw)
