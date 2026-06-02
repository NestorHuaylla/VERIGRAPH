from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EntityType, RiskLevel
from app.models.entity import Entity
from app.models.report import Report
from app.models.risk import RiskScore
from app.schemas.risk import PublicRiskResponse, RiskSignal
from app.services.entities import find_entity_by_normalized_value
from app.services.external_reputation import build_external_risk_signals, list_latest_external_reputation_checks
from app.services.normalizer import NormalizedEntity, infer_entity_type, normalize_entity
from app.services.scoring import ScoreResult, calculate_initial_score


async def lookup_public_risk(
    db: AsyncSession,
    *,
    value: str,
    entity_type: EntityType | None = None,
) -> PublicRiskResponse:
    inferred_type = entity_type or infer_entity_type(value)
    normalized = normalize_entity(inferred_type, value)
    entity = await find_entity_by_normalized_value(
        db,
        entity_type=inferred_type,
        normalized_value=normalized.value,
    )

    related_reports = await count_related_reports(db, entity) if entity else 0
    latest_score = await find_latest_risk_score(db, entity) if entity else None
    external_checks = await list_latest_external_reputation_checks(db, entity) if entity else []

    return build_public_risk_response(
        raw_value=value,
        entity_type=inferred_type,
        normalized=normalized,
        entity=entity,
        related_reports=related_reports,
        latest_score=latest_score,
        external_signals=build_external_risk_signals(external_checks),
    )


async def count_related_reports(db: AsyncSession, entity: Entity) -> int:
    result = await db.execute(select(func.count(Report.id)).where(Report.entity_id == entity.id))
    return int(result.scalar_one())


async def find_latest_risk_score(db: AsyncSession, entity: Entity) -> RiskScore | None:
    result = await db.execute(
        select(RiskScore)
        .where(RiskScore.entity_id == entity.id)
        .order_by(desc(RiskScore.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


def build_public_risk_response(
    *,
    raw_value: str,
    entity_type: EntityType,
    normalized: NormalizedEntity,
    entity: Entity | None,
    related_reports: int,
    latest_score: RiskScore | None,
    external_signals: list[RiskSignal] | None = None,
) -> PublicRiskResponse:
    if latest_score:
        return PublicRiskResponse(
            entity_type=entity_type,
            normalized_value=normalized.value,
            entity_id=str(entity.id) if entity else None,
            related_reports=related_reports,
            score=latest_score.score,
            level=RiskLevel(latest_score.level),
            explanation=latest_score.explanation,
            signals=parse_stored_signals(latest_score.signals),
            data_source="stored",
        )

    fallback = calculate_initial_score(
        text=raw_value,
        entity_type=entity_type,
        normalized_value=normalized.value,
        external_signals=external_signals,
    )
    return build_computed_public_risk_response(
        entity_type=entity_type,
        normalized=normalized,
        entity=entity,
        related_reports=related_reports,
        score=fallback,
    )


def build_computed_public_risk_response(
    *,
    entity_type: EntityType,
    normalized: NormalizedEntity,
    entity: Entity | None,
    related_reports: int,
    score: ScoreResult,
) -> PublicRiskResponse:
    return PublicRiskResponse(
        entity_type=entity_type,
        normalized_value=normalized.value,
        entity_id=str(entity.id) if entity else None,
        related_reports=related_reports,
        score=score.score,
        level=score.level,
        explanation=build_public_explanation(score.explanation, related_reports),
        signals=score.signals,
        data_source="computed",
    )


def parse_stored_signals(signals: dict | None) -> list[RiskSignal]:
    items = (signals or {}).get("items", [])
    parsed: list[RiskSignal] = []
    for item in items:
        try:
            parsed.append(RiskSignal.model_validate(item))
        except ValueError:
            continue
    return parsed


def build_public_explanation(base_explanation: str, related_reports: int) -> str:
    if related_reports <= 0:
        return base_explanation
    return f"{base_explanation} Existen {related_reports} reportes relacionados en revision."
