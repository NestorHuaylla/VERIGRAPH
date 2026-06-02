from app.core.constants import EntityType
from app.services.indicators import extract_indicators
from app.services.normalizer import normalize_entity


def normalize_keys(text: str) -> set[tuple[EntityType, str]]:
    return {
        (indicator.entity_type, normalize_entity(indicator.entity_type, indicator.raw_value).value)
        for indicator in extract_indicators(text)
    }


def test_extract_indicators_from_report_reason() -> None:
    keys = normalize_keys(
        "Revisa https://www.estafa-peru.com/oferta, WhatsApp +51 999 999 999, "
        "wallet 0xABCDEF1234567890ABCDEF1234567890ABCDEF12 y canal t.me/canal_demo."
    )

    assert (EntityType.URL, "https://estafa-peru.com/oferta") in keys
    assert (EntityType.PHONE, "+51999999999") in keys
    assert (EntityType.WALLET, "evm:0xabcdef1234567890abcdef1234567890abcdef12") in keys
    assert (EntityType.SOCIAL_CHANNEL, "telegram:canal_demo") in keys


def test_extract_indicators_deduplicates_equivalent_values() -> None:
    indicators = extract_indicators("Contacto +51 999 999 999 o wa.me/51999999999")
    phone_indicators = [indicator for indicator in indicators if indicator.entity_type == EntityType.PHONE]

    assert len(phone_indicators) == 1


def test_extract_indicators_does_not_treat_email_domain_as_domain_indicator() -> None:
    keys = normalize_keys("Escribe a soporte@empresa.com y revisa empresa.com/alerta")

    assert (EntityType.EMAIL, "soporte@empresa.com") in keys
    assert (EntityType.DOMAIN, "empresa.com") in keys
