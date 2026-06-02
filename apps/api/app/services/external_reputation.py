from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.external_reputation import ExternalReputationCheck
from app.schemas.external_reputation import (
    ExternalReputationBatchCreate,
    ExternalReputationCheckCreate,
    ExternalReputationCheckResponse,
    ExternalReputationSummary,
)
from app.schemas.risk import RiskSignal
from app.services.entities import find_entity_by_id
from app.services.notifications import create_external_reputation_notification


EXTERNAL_SCORING_RULES_VERSION = "external-v1"
CHECKED_STATUSES = {"clean", "malicious", "unknown", "error"}


class EntityNotFoundError(Exception):
    def __init__(self, entity_id: UUID) -> None:
        super().__init__(f"Entity {entity_id} was not found.")
        self.entity_id = entity_id


@dataclass(frozen=True)
class ExternalReputationBatchResult:
    checks: list[ExternalReputationCheck]
    summary: ExternalReputationSummary


async def create_external_reputation_checks(
    db: AsyncSession,
    entity_id: UUID,
    payload: ExternalReputationBatchCreate,
) -> ExternalReputationBatchResult:
    entity = await find_entity_by_id(db, entity_id)
    if entity is None:
        raise EntityNotFoundError(entity_id)

    checks = [
        build_external_reputation_check(entity, check_payload, batch_metadata=payload.metadata)
        for check_payload in payload.checks
    ]
    for check in checks:
        db.add(check)

    summary = build_external_reputation_summary(checks)
    await create_external_reputation_notification(
        db,
        entity=entity,
        checks=checks,
        summary=summary,
    )

    await db.commit()
    for check in checks:
        await db.refresh(check)

    return ExternalReputationBatchResult(
        checks=checks,
        summary=summary,
    )


async def list_external_reputation_checks(
    db: AsyncSession,
    entity_id: UUID,
    *,
    limit: int = 50,
    source: str | None = None,
) -> list[ExternalReputationCheck]:
    statement = (
        select(ExternalReputationCheck)
        .where(ExternalReputationCheck.entity_id == entity_id)
        .order_by(desc(ExternalReputationCheck.created_at))
        .limit(limit)
    )
    if source:
        statement = statement.where(ExternalReputationCheck.source == source)

    result = await db.execute(statement)
    return list(result.scalars().all())


async def list_latest_external_reputation_checks(
    db: AsyncSession,
    entity: Entity,
    *,
    limit: int = 10,
) -> list[ExternalReputationCheck]:
    result = await db.execute(
        select(ExternalReputationCheck)
        .where(ExternalReputationCheck.entity_id == entity.id)
        .order_by(desc(ExternalReputationCheck.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


def build_external_reputation_check(
    entity: Entity,
    payload: ExternalReputationCheckCreate,
    *,
    batch_metadata: dict | None = None,
) -> ExternalReputationCheck:
    metadata = dict(batch_metadata or {})
    metadata.update(payload.metadata or {})
    return ExternalReputationCheck(
        entity_id=entity.id,
        source=payload.source,
        status=payload.status,
        severity=payload.severity,
        malicious=payload.malicious,
        summary=payload.summary,
        reference=payload.reference,
        raw=payload.raw or {},
        metadata_json=metadata,
    )


def build_external_reputation_summary(checks: list[ExternalReputationCheck]) -> ExternalReputationSummary:
    malicious_sources = sorted({check.source for check in checks if check.malicious})
    checked_sources = sorted({check.source for check in checks if check.status in CHECKED_STATUSES})
    return ExternalReputationSummary(
        malicious=bool(malicious_sources),
        malicious_sources=malicious_sources,
        checked_sources=checked_sources,
        highest_severity=highest_external_severity(checks),
    )


def highest_external_severity(checks: list[ExternalReputationCheck]) -> str:
    order = {"none": 0, "unknown": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}
    selected = "none"
    for check in checks:
        if order.get(check.severity, 0) > order[selected]:
            selected = check.severity
    return selected


def build_external_reputation_response(check: ExternalReputationCheck) -> ExternalReputationCheckResponse:
    return ExternalReputationCheckResponse(
        id=check.id,
        entity_id=check.entity_id,
        source=check.source,
        status=check.status,
        malicious=check.malicious,
        severity=check.severity,
        summary=check.summary,
        reference=check.reference,
        raw=check.raw or {},
        metadata=check.metadata_json or {},
        created_at=check.created_at.isoformat(),
    )


def build_external_risk_signals(checks: list[ExternalReputationCheck]) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    malicious_checks = [check for check in checks if check.malicious]
    if not malicious_checks:
        return signals

    high_sources = sorted({check.source for check in malicious_checks if check.severity in {"high", "critical"}})
    other_sources = sorted({check.source for check in malicious_checks if check.severity not in {"high", "critical"}})

    if high_sources:
        signals.append(
            RiskSignal(
                code="external_high_confidence_match",
                label=f"Fuente externa marco la entidad como maliciosa: {', '.join(high_sources)}",
                weight=18,
            )
        )
    if other_sources:
        signals.append(
            RiskSignal(
                code="external_reputation_match",
                label=f"Fuente externa reporto reputacion negativa: {', '.join(other_sources)}",
                weight=10,
            )
        )

    return signals
