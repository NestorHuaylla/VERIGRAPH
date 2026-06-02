import pytest

from app.core.constants import EntityType
from app.services.normalizer import infer_entity_type, normalize_entity


@pytest.mark.parametrize(
    "raw",
    [
        "+51 999 999 999",
        "51999999999",
        "999999999",
        "wa.me/51999999999",
        "https://wa.me/51999999999?text=hola",
    ],
)
def test_normalize_phone_variants(raw: str) -> None:
    normalized = normalize_entity(EntityType.PHONE, raw)

    assert normalized.value == "+51999999999"
    assert normalized.display_value == "+51999999999"


@pytest.mark.parametrize(
    "raw",
    [
        "wa.me/51999999999",
        "https://wa.me/51999999999?text=hola",
        "+51 999 999 999",
    ],
)
def test_infer_phone_variants(raw: str) -> None:
    assert infer_entity_type(raw) == EntityType.PHONE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("www.Estafa-Peru.com", "estafa-peru.com"),
        ("https://www.Estafa-Peru.com/oferta", "estafa-peru.com"),
        ("ESTAFA-PERU.COM/Oferta", "estafa-peru.com"),
        ("estafa-peru.com.", "estafa-peru.com"),
    ],
)
def test_normalize_domain_variants(raw: str, expected: str) -> None:
    normalized = normalize_entity(EntityType.DOMAIN, raw)

    assert normalized.value == expected
    assert normalized.display_value == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.Estafa-Peru.com/oferta/", "https://estafa-peru.com/oferta"),
        ("http://estafa-peru.com/oferta", "http://estafa-peru.com/oferta"),
        ("estafa-peru.com/oferta", "https://estafa-peru.com/oferta"),
        ("https://estafa-peru.com/oferta?utm_source=tiktok", "https://estafa-peru.com/oferta"),
        ("https://estafa-peru.com/oferta#comentarios", "https://estafa-peru.com/oferta"),
    ],
)
def test_normalize_url_variants(raw: str, expected: str) -> None:
    normalized = normalize_entity(EntityType.URL, raw)

    assert normalized.value == expected
    assert normalized.display_value == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Demo@Example.COM ", "demo@example.com"),
        ("reportes+fraude@Example.COM", "reportes+fraude@example.com"),
    ],
)
def test_normalize_email_variants(raw: str, expected: str) -> None:
    normalized = normalize_entity(EntityType.EMAIL, raw)

    assert normalized.value == expected
    assert normalized.display_value == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("t.me/canal_demo", "telegram:canal_demo"),
        ("https://t.me/canal_demo", "telegram:canal_demo"),
        ("telegram.me/Canal_Demo", "telegram:canal_demo"),
        ("https://t.me/s/canal_demo", "telegram:canal_demo"),
        ("@canal_demo", "telegram:canal_demo"),
    ],
)
def test_normalize_telegram_variants(raw: str, expected: str) -> None:
    normalized = normalize_entity(EntityType.SOCIAL_CHANNEL, raw)

    assert normalized.value == expected
    assert normalized.display_value == expected


@pytest.mark.parametrize(
    "raw",
    [
        "t.me/canal_demo",
        "https://t.me/canal_demo",
        "telegram.me/canal_demo",
        "@canal_demo",
    ],
)
def test_infer_telegram_variants(raw: str) -> None:
    assert infer_entity_type(raw) == EntityType.SOCIAL_CHANNEL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
            "evm:0xabcdef1234567890abcdef1234567890abcdef12",
        ),
        (
            "ETH: 0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
            "evm:0xabcdef1234567890abcdef1234567890abcdef12",
        ),
        (
            "bc1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KYGT080",
            "btc:bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kygt080",
        ),
        (
            "1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
            "btc:1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
        ),
        (
            "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
            "btc:3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
        ),
        (
            "tron:TJRyWwFs9wTFGZg3JbrVriFbNfCug5tDeC",
            "trx:TJRyWwFs9wTFGZg3JbrVriFbNfCug5tDeC",
        ),
        ("MiWallet123", "wallet:miwallet123"),
    ],
)
def test_normalize_wallet_variants(raw: str, expected: str) -> None:
    normalized = normalize_entity(EntityType.WALLET, raw)

    assert normalized.value == expected
    assert normalized.display_value == expected


@pytest.mark.parametrize(
    "raw",
    [
        "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
        "ETH: 0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
        "bc1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KYGT080",
        "1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
        "tron:TJRyWwFs9wTFGZg3JbrVriFbNfCug5tDeC",
    ],
)
def test_infer_wallet_variants(raw: str) -> None:
    assert infer_entity_type(raw) == EntityType.WALLET
