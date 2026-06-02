from uuid import uuid4

from app.core.constants import EntityType, RiskLevel
from app.models.entity import Entity
from app.models.risk import RiskScore
from app.services.normalizer import normalize_entity
from app.services.risk_lookup import build_public_risk_response, parse_stored_signals


def build_entity() -> Entity:
    entity = Entity(
        type="phone",
        raw_value="+51 999 999 999",
        normalized_value="+51999999999",
        display_value="+51999999999",
        metadata_json={"created_from": "test"},
    )
    entity.id = uuid4()
    return entity


def test_build_public_risk_response_uses_stored_score() -> None:
    entity = build_entity()
    normalized = normalize_entity(EntityType.PHONE, "wa.me/51999999999")
    risk_score = RiskScore(
        entity_id=entity.id,
        score=14,
        level="medium",
        explanation="Riesgo medio por reportes relacionados.",
        signals={"items": [{"code": "related_reports", "label": "Reportes relacionados", "weight": 6}]},
        rules_version="v1",
    )

    response = build_public_risk_response(
        raw_value="wa.me/51999999999",
        entity_type=EntityType.PHONE,
        normalized=normalized,
        entity=entity,
        related_reports=3,
        latest_score=risk_score,
    )

    assert response.entity_type == EntityType.PHONE
    assert response.normalized_value == "+51999999999"
    assert response.entity_id == str(entity.id)
    assert response.related_reports == 3
    assert response.score == 14
    assert response.level == RiskLevel.MEDIUM
    assert response.data_source == "stored"
    assert response.signals[0].code == "related_reports"


def test_build_public_risk_response_computes_fallback_without_stored_score() -> None:
    normalized = normalize_entity(EntityType.URL, "https://www.estafa-peru.com/oferta")

    response = build_public_risk_response(
        raw_value="https://www.estafa-peru.com/oferta",
        entity_type=EntityType.URL,
        normalized=normalized,
        entity=None,
        related_reports=0,
        latest_score=None,
    )

    assert response.entity_type == EntityType.URL
    assert response.normalized_value == "https://estafa-peru.com/oferta"
    assert response.entity_id is None
    assert response.related_reports == 0
    assert response.score == 2
    assert response.level == RiskLevel.LOW
    assert response.data_source == "computed"


def test_build_public_risk_response_mentions_related_reports_without_score() -> None:
    entity = build_entity()
    normalized = normalize_entity(EntityType.PHONE, "+51 999 999 999")

    response = build_public_risk_response(
        raw_value="+51 999 999 999",
        entity_type=EntityType.PHONE,
        normalized=normalized,
        entity=entity,
        related_reports=2,
        latest_score=None,
    )

    assert response.related_reports == 2
    assert "2 reportes relacionados" in response.explanation


def test_parse_stored_signals_ignores_invalid_items() -> None:
    signals = parse_stored_signals({"items": [{"code": "ok", "label": "OK", "weight": 1}, {"bad": "item"}]})

    assert len(signals) == 1
    assert signals[0].code == "ok"
