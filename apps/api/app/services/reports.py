from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ReviewStatus, RiskLevel
from app.models.entity import Entity
from app.models.report import Report
from app.models.risk import RiskScore
from app.schemas.report import ReportCreate, ReportDetailResponse, ReportListItem, ReportStatusUpdate
from app.schemas.risk import RiskSignal
from app.services.abuse import validate_public_report
from app.services.audit import write_audit_log
from app.services.entities import EntityResolution, get_or_create_entity
from app.services.graph_engine import calculate_entity_graph_metrics
from app.services.normalizer import NormalizedEntity
from app.services.notifications import create_report_risk_notification
from app.services.relations import create_report_entity_relations
from app.services.scoring import RULES_VERSION, ScoreResult, calculate_initial_score


@dataclass(frozen=True)
class ReportCreationResult:
    report: Report
    entity: Entity
    normalized: NormalizedEntity
    risk: ScoreResult
    entity_created: bool
    relations_created: int


class ReportNotFoundError(Exception):
    def __init__(self, report_id: UUID) -> None:
        super().__init__(f"Report {report_id} was not found.")
        self.report_id = report_id


async def list_reports(db: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[ReportListItem]:
    latest_scores = (
        select(
            RiskScore.entity_id.label("entity_id"),
            func.max(RiskScore.created_at).label("created_at"),
        )
        .group_by(RiskScore.entity_id)
        .subquery()
    )

    statement = (
        select(Report, Entity, RiskScore)
        .outerjoin(Entity, Report.entity_id == Entity.id)
        .outerjoin(latest_scores, latest_scores.c.entity_id == Report.entity_id)
        .outerjoin(
            RiskScore,
            and_(
                RiskScore.entity_id == latest_scores.c.entity_id,
                RiskScore.created_at == latest_scores.c.created_at,
            ),
        )
        .order_by(desc(Report.created_at))
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(statement)
    return [build_report_list_item(report, entity, risk_score) for report, entity, risk_score in result.all()]


async def get_report_detail(db: AsyncSession, report_id: UUID) -> ReportDetailResponse:
    result = await db.execute(
        select(Report, Entity)
        .outerjoin(Entity, Report.entity_id == Entity.id)
        .where(Report.id == report_id)
    )
    row = result.one_or_none()
    if row is None:
        raise ReportNotFoundError(report_id)

    report, entity = row
    risk_score = None
    if report.entity_id is not None:
        risk_result = await db.execute(
            select(RiskScore)
            .where(RiskScore.entity_id == report.entity_id)
            .order_by(desc(RiskScore.created_at))
            .limit(1)
        )
        risk_score = risk_result.scalar_one_or_none()

    return build_report_detail(report, entity, risk_score)


async def find_report_by_id(db: AsyncSession, report_id: UUID) -> Report | None:
    result = await db.execute(select(Report).where(Report.id == report_id))
    return result.scalar_one_or_none()


async def update_report_status(
    db: AsyncSession,
    report_id: UUID,
    payload: ReportStatusUpdate,
    *,
    actor_user_id: UUID | None = None,
) -> Report:
    report = await find_report_by_id(db, report_id)
    if report is None:
        raise ReportNotFoundError(report_id)

    old_status, new_status = apply_report_status_update(report, payload)
    await write_report_status_changed_audit_log(
        db,
        report,
        old_status=old_status,
        new_status=new_status,
        reason=payload.reason,
        actor_user_id=actor_user_id,
    )

    await db.commit()
    await db.refresh(report)

    return report


async def create_report(
    db: AsyncSession,
    payload: ReportCreate,
    *,
    source: str = "public_form",
    request_metadata: dict | None = None,
) -> ReportCreationResult:
    if source == "public_form":
        validate_public_report(payload)

    resolution = await get_or_create_entity(
        db,
        entity_type=payload.entity_type,
        raw_value=payload.entity_value,
        source="public_report",
    )
    base_risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )

    report = build_report(payload, resolution, base_risk, source=source, request_metadata=request_metadata)
    db.add(report)
    await db.flush()

    relations = await create_report_entity_relations(
        db,
        source_entity=resolution.entity,
        report_id=report.id,
        text=payload.reason,
    )
    graph_metrics = await calculate_entity_graph_metrics(db, entity_id=resolution.entity.id)
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
        graph_degree=graph_metrics.degree,
    )
    update_report_initial_risk(report, risk)
    db.add(build_risk_score(resolution.entity, risk))
    await create_report_risk_notification(
        db,
        report=report,
        entity=resolution.entity,
        risk=risk,
        relations_created=len(relations),
        graph_degree=graph_metrics.degree,
    )
    await write_report_created_audit_log(
        db,
        payload,
        resolution,
        risk,
        report,
        relations_created=len(relations),
        graph_degree=graph_metrics.degree,
        source=source,
    )

    await db.commit()
    await db.refresh(report)

    return ReportCreationResult(
        report=report,
        entity=resolution.entity,
        normalized=resolution.normalized,
        risk=risk,
        entity_created=resolution.created,
        relations_created=len(relations),
    )


def build_report_list_item(
    report: Report,
    entity: Entity | None,
    risk_score: RiskScore | None,
) -> ReportListItem:
    metadata = report.metadata_json or {}
    score = risk_score.score if risk_score else metadata.get("initial_risk_score")
    level = risk_score.level if risk_score else metadata.get("initial_risk_level")

    return ReportListItem(
        id=str(report.id),
        entity_id=str(entity.id) if entity else None,
        entity_type=entity.type if entity else None,
        entity_value=entity.display_value if entity else None,
        entity_normalized_value=entity.normalized_value if entity else None,
        status=report.status,
        risk_score=score,
        risk_level=level,
        created_at=report.created_at,
    )


def build_report_detail(
    report: Report,
    entity: Entity | None,
    risk_score: RiskScore | None,
) -> ReportDetailResponse:
    metadata = dict(report.metadata_json or {})
    score = risk_score.score if risk_score else metadata.get("initial_risk_score")
    level = risk_score.level if risk_score else metadata.get("initial_risk_level")

    return ReportDetailResponse(
        id=str(report.id),
        entity_id=str(entity.id) if entity else None,
        entity_type=entity.type if entity else None,
        entity_value=entity.display_value if entity else None,
        entity_raw_value=entity.raw_value if entity else metadata.get("entity_raw_value"),
        entity_normalized_value=entity.normalized_value if entity else metadata.get("entity_normalized_value"),
        reporter_contact=report.reporter_contact,
        reason=report.reason,
        status=ReviewStatus(report.status),
        source=report.source,
        risk_score=score,
        risk_level=RiskLevel(level) if level else None,
        risk_explanation=risk_score.explanation if risk_score else None,
        risk_signals=parse_risk_signals(risk_score.signals if risk_score else None),
        risk_rules_version=risk_score.rules_version if risk_score else None,
        metadata=metadata,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def apply_report_status_update(report: Report, payload: ReportStatusUpdate) -> tuple[str, ReviewStatus]:
    old_status = report.status
    metadata = dict(report.metadata_json or {})
    status_history = list(metadata.get("status_history") or [])
    status_history.append(
        {
            "from": old_status,
            "to": payload.status.value,
            "reason": payload.reason,
        }
    )
    metadata["status_history"] = status_history
    metadata["last_status_reason"] = payload.reason

    report.status = payload.status.value
    report.metadata_json = metadata

    return old_status, payload.status


def parse_risk_signals(raw_signals: dict | None) -> list[RiskSignal]:
    items = (raw_signals or {}).get("items") or []
    return [RiskSignal.model_validate(item) for item in items]


def build_report(
    payload: ReportCreate,
    resolution: EntityResolution,
    risk: ScoreResult,
    *,
    source: str,
    request_metadata: dict | None = None,
) -> Report:
    metadata = {
        "entity_raw_value": payload.entity_value,
        "entity_normalized_value": resolution.normalized.value,
        "initial_risk_score": risk.score,
        "initial_risk_level": risk.level.value,
    }
    metadata.update(request_metadata or {})

    return Report(
        entity_id=resolution.entity.id,
        reporter_contact=str(payload.reporter_contact) if payload.reporter_contact else None,
        reason=payload.reason,
        status="pending",
        source=source,
        metadata_json=metadata,
    )


def update_report_initial_risk(report: Report, risk: ScoreResult) -> None:
    metadata = dict(report.metadata_json or {})
    metadata["initial_risk_score"] = risk.score
    metadata["initial_risk_level"] = risk.level.value
    report.metadata_json = metadata


def build_risk_score(entity: Entity, risk: ScoreResult) -> RiskScore:
    return RiskScore(
        entity_id=entity.id,
        score=risk.score,
        level=risk.level.value,
        explanation=risk.explanation,
        signals={"items": [signal.model_dump() for signal in risk.signals]},
        rules_version=RULES_VERSION,
    )


async def write_report_created_audit_log(
    db: AsyncSession,
    payload: ReportCreate,
    resolution: EntityResolution,
    risk: ScoreResult,
    report: Report,
    *,
    relations_created: int = 0,
    graph_degree: int = 0,
    source: str,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=None,
        action="report.created",
        target_type="report",
        target_id=str(report.id),
        metadata={
            "entity_id": str(resolution.entity.id),
            "entity_type": payload.entity_type.value,
            "entity_normalized_value": resolution.normalized.value,
            "entity_created": resolution.created,
            "risk_score": risk.score,
            "risk_level": risk.level.value,
            "relations_created": relations_created,
            "graph_degree": graph_degree,
            "source": source,
        },
    )


async def write_report_status_changed_audit_log(
    db: AsyncSession,
    report: Report,
    *,
    old_status: str,
    new_status: ReviewStatus,
    reason: str,
    actor_user_id: UUID | None = None,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="report.status_changed",
        target_type="report",
        target_id=str(report.id),
        metadata={
            "old_status": old_status,
            "new_status": new_status.value,
            "reason": reason,
        },
    )
