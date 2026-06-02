from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CaseStatus, EntityType, RiskLevel
from app.models.case import Case
from app.models.entity import Entity, EntityRelation
from app.models.evidence import EvidenceFile
from app.models.report import Report
from app.models.risk import RiskScore
from app.schemas.case import (
    CaseCreate,
    CaseDetailResponse,
    CaseEntityContext,
    CaseListItem,
    CaseReportItem,
    CaseStatusUpdate,
)
from app.schemas.graph import GraphMetrics, GraphResponse
from app.services.audit import write_audit_log
from app.services.case_scoring import CaseScoreResult, calculate_case_score
from app.services.graph_engine import build_entity_graph, calculate_entity_graph_metrics
from app.services.notifications import create_case_risk_notification


DEFAULT_CASE_LIMIT = 100
DEFAULT_CASE_GRAPH_LIMIT = 100
DEFAULT_CASE_REPORT_LIMIT = 50


class EntityNotFoundError(Exception):
    def __init__(self, entity_id: UUID) -> None:
        super().__init__(f"Entity {entity_id} was not found.")
        self.entity_id = entity_id


class CaseNotFoundError(Exception):
    def __init__(self, case_id: UUID) -> None:
        super().__init__(f"Case {case_id} was not found.")
        self.case_id = case_id


async def create_case_from_entity(
    db: AsyncSession,
    entity_id: UUID,
    payload: CaseCreate | None = None,
    *,
    actor_user_id: UUID | None = None,
) -> Case:
    entity = await find_entity_by_id(db, entity_id)
    if entity is None:
        raise EntityNotFoundError(entity_id)

    existing_case = await find_case_by_root_entity_id(db, entity_id)
    if existing_case is not None:
        await write_case_reused_audit_log(db, existing_case, actor_user_id=actor_user_id)
        await db.commit()
        await db.refresh(existing_case)
        return existing_case

    latest_risk_score = await find_latest_risk_score(db, entity_id)
    case = build_case_from_entity(entity, latest_risk_score, payload or CaseCreate())
    db.add(case)
    await db.flush()
    await write_case_created_audit_log(db, case, actor_user_id=actor_user_id)

    await db.commit()
    await db.refresh(case)

    return case


async def list_cases(
    db: AsyncSession,
    *,
    limit: int = DEFAULT_CASE_LIMIT,
    offset: int = 0,
) -> list[CaseListItem]:
    result = await db.execute(select(Case).order_by(desc(Case.created_at)).limit(limit).offset(offset))
    return [build_case_list_item(case) for case in result.scalars().all()]


async def get_case_detail(db: AsyncSession, case_id: UUID) -> CaseDetailResponse:
    case = await find_case_by_id(db, case_id)
    if case is None:
        raise CaseNotFoundError(case_id)

    root_entity = None
    graph = GraphResponse(nodes=[], edges=[])
    graph_metrics = None
    reports: list[CaseReportItem] = []
    evidence_count = 0

    root_entity_id = get_case_root_entity_id(case)
    if root_entity_id is not None:
        root_entity = await find_entity_by_id(db, root_entity_id)
        if root_entity is not None:
            graph = await build_entity_graph(db, entity_id=root_entity.id, limit=DEFAULT_CASE_GRAPH_LIMIT)
            graph_metrics = await calculate_entity_graph_metrics(db, entity_id=root_entity.id)
            reports = await list_case_reports(db, root_entity.id)
            evidence_count = await count_evidence_for_reports(db, [UUID(report.id) for report in reports])

    return build_case_detail(
        case,
        root_entity=root_entity,
        reports=reports,
        evidence_count=evidence_count,
        graph=graph,
        graph_metrics=graph_metrics,
    )


async def update_case_status(
    db: AsyncSession,
    case_id: UUID,
    payload: CaseStatusUpdate,
    *,
    actor_user_id: UUID | None = None,
) -> Case:
    case = await find_case_by_id(db, case_id)
    if case is None:
        raise CaseNotFoundError(case_id)

    old_status, new_status = apply_case_status_update(case, payload)
    await write_case_status_changed_audit_log(
        db,
        case,
        old_status=old_status,
        new_status=new_status,
        reason=payload.reason,
        actor_user_id=actor_user_id,
    )

    await db.commit()
    await db.refresh(case)

    return case


async def sync_case_snapshot(
    db: AsyncSession,
    case_id: UUID,
    *,
    actor_user_id: UUID | None = None,
) -> Case:
    case = await find_case_by_id(db, case_id)
    if case is None:
        raise CaseNotFoundError(case_id)

    previous_snapshot = (case.metadata_json or {}).get("snapshot") or {}
    snapshot = await build_case_snapshot(db, case)
    apply_case_snapshot(case, snapshot)
    enriched_snapshot = (case.metadata_json or {}).get("snapshot", snapshot)
    await create_case_risk_notification(
        db,
        case,
        snapshot=enriched_snapshot,
        previous_snapshot=previous_snapshot,
    )
    await write_case_synced_audit_log(
        db,
        case,
        snapshot=enriched_snapshot,
        actor_user_id=actor_user_id,
    )

    await db.commit()
    await db.refresh(case)

    return case


async def find_entity_by_id(db: AsyncSession, entity_id: UUID) -> Entity | None:
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    return result.scalar_one_or_none()


async def find_case_by_id(db: AsyncSession, case_id: UUID) -> Case | None:
    result = await db.execute(select(Case).where(Case.id == case_id))
    return result.scalar_one_or_none()


async def find_case_by_root_entity_id(db: AsyncSession, entity_id: UUID) -> Case | None:
    result = await db.execute(
        select(Case).where(Case.metadata_json["root_entity_id"].astext == str(entity_id)).limit(1)
    )
    return result.scalar_one_or_none()


async def find_latest_risk_score(db: AsyncSession, entity_id: UUID) -> RiskScore | None:
    result = await db.execute(
        select(RiskScore)
        .where(RiskScore.entity_id == entity_id)
        .order_by(desc(RiskScore.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_case_reports(
    db: AsyncSession,
    entity_id: UUID,
    *,
    limit: int = DEFAULT_CASE_REPORT_LIMIT,
) -> list[CaseReportItem]:
    result = await db.execute(
        select(Report)
        .where(Report.entity_id == entity_id)
        .order_by(desc(Report.created_at))
        .limit(limit)
    )
    return [build_case_report_item(report) for report in result.scalars().all()]


async def count_evidence_for_reports(db: AsyncSession, report_ids: list[UUID]) -> int:
    if not report_ids:
        return 0

    result = await db.execute(select(func.count(EvidenceFile.id)).where(EvidenceFile.report_id.in_(report_ids)))
    return int(result.scalar_one())


async def count_reports_for_entity(db: AsyncSession, entity_id: UUID) -> int:
    result = await db.execute(select(func.count(Report.id)).where(Report.entity_id == entity_id))
    return int(result.scalar_one())


async def count_relations_for_entity(db: AsyncSession, entity_id: UUID) -> int:
    result = await db.execute(
        select(func.count(EntityRelation.id)).where(
            (EntityRelation.source_entity_id == entity_id) | (EntityRelation.target_entity_id == entity_id)
        )
    )
    return int(result.scalar_one())


async def build_case_snapshot(db: AsyncSession, case: Case) -> dict:
    root_entity_id = get_case_root_entity_id(case)
    if root_entity_id is None:
        return {
            "root_entity_id": None,
            "reports_count": 0,
            "evidence_count": 0,
            "graph_nodes_count": 0,
            "graph_edges_count": 0,
            "graph_degree": 0,
            "risk_level": case.risk_level,
            "risk_score": None,
        }

    reports = await list_case_reports(db, root_entity_id, limit=DEFAULT_CASE_REPORT_LIMIT)
    report_ids = [UUID(report.id) for report in reports]
    evidence_count = await count_evidence_for_reports(db, report_ids)
    graph = await build_entity_graph(db, entity_id=root_entity_id, limit=DEFAULT_CASE_GRAPH_LIMIT)
    graph_metrics = await calculate_entity_graph_metrics(db, entity_id=root_entity_id)
    latest_risk_score = await find_latest_risk_score(db, root_entity_id)
    reports_count = await count_reports_for_entity(db, root_entity_id)
    relations_count = await count_relations_for_entity(db, root_entity_id)

    return {
        "root_entity_id": str(root_entity_id),
        "reports_count": reports_count,
        "evidence_count": evidence_count,
        "graph_nodes_count": len(graph.nodes),
        "graph_edges_count": len(graph.edges),
        "graph_degree": graph_metrics.degree,
        "relations_count": relations_count,
        "risk_level": latest_risk_score.level if latest_risk_score else case.risk_level,
        "risk_score": latest_risk_score.score if latest_risk_score else None,
    }


def build_case_from_entity(
    entity: Entity,
    latest_risk_score: RiskScore | None,
    payload: CaseCreate,
) -> Case:
    risk_level = latest_risk_score.level if latest_risk_score else RiskLevel.MEDIUM.value
    return Case(
        title=payload.title or build_default_case_title(entity),
        summary=payload.summary,
        status=CaseStatus.OPEN.value,
        risk_level=risk_level,
        metadata_json={
            "root_entity_id": str(entity.id),
            "root_entity_type": entity.type,
            "root_entity_value": entity.display_value,
            "root_entity_normalized_value": entity.normalized_value,
            "initial_risk_level": risk_level,
            "initial_risk_score": latest_risk_score.score if latest_risk_score else None,
        },
    )


def build_default_case_title(entity: Entity) -> str:
    return f"{entity.type}: {entity.display_value}"[:255]


def build_case_list_item(case: Case) -> CaseListItem:
    metadata = case.metadata_json or {}
    return CaseListItem(
        id=str(case.id),
        title=case.title,
        summary=case.summary,
        status=CaseStatus(case.status),
        risk_level=RiskLevel(case.risk_level),
        root_entity_id=metadata.get("root_entity_id"),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def build_case_detail(
    case: Case,
    *,
    root_entity: Entity | None,
    reports: list[CaseReportItem],
    evidence_count: int,
    graph: GraphResponse,
    graph_metrics: GraphMetrics | None,
) -> CaseDetailResponse:
    return CaseDetailResponse(
        id=str(case.id),
        title=case.title,
        summary=case.summary,
        status=CaseStatus(case.status),
        risk_level=RiskLevel(case.risk_level),
        root_entity=build_case_entity_context(root_entity) if root_entity else None,
        reports=reports,
        evidence_count=evidence_count,
        graph=graph,
        graph_metrics=graph_metrics,
        metadata=case.metadata_json or {},
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def build_case_entity_context(entity: Entity) -> CaseEntityContext:
    return CaseEntityContext(
        id=str(entity.id),
        type=EntityType(entity.type),
        display_value=entity.display_value,
        normalized_value=entity.normalized_value,
    )


def build_case_report_item(report: Report) -> CaseReportItem:
    return CaseReportItem(
        id=str(report.id),
        status=report.status,
        reason=report.reason,
        source=report.source,
        created_at=report.created_at,
    )


def apply_case_status_update(case: Case, payload: CaseStatusUpdate) -> tuple[str, CaseStatus]:
    old_status = case.status
    metadata = dict(case.metadata_json or {})
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

    case.status = payload.status.value
    case.metadata_json = metadata

    return old_status, payload.status


def apply_case_snapshot(case: Case, snapshot: dict) -> None:
    case_score = calculate_case_score(snapshot)
    enriched_snapshot = enrich_case_snapshot_with_score(snapshot, case_score)
    metadata = dict(case.metadata_json or {})
    metadata["snapshot"] = enriched_snapshot
    case.metadata_json = metadata
    case.risk_level = case_score.level.value


def enrich_case_snapshot_with_score(snapshot: dict, case_score: CaseScoreResult) -> dict:
    enriched_snapshot = dict(snapshot)
    enriched_snapshot["case_score"] = case_score.score
    enriched_snapshot["case_risk_level"] = case_score.level.value
    enriched_snapshot["case_scoring_explanation"] = case_score.explanation
    enriched_snapshot["case_scoring_rules_version"] = case_score.rules_version
    enriched_snapshot["case_scoring_signals"] = [signal.model_dump() for signal in case_score.signals]
    return enriched_snapshot


def get_case_root_entity_id(case: Case) -> UUID | None:
    root_entity_id = (case.metadata_json or {}).get("root_entity_id")
    if not root_entity_id:
        return None
    return UUID(str(root_entity_id))


async def write_case_created_audit_log(
    db: AsyncSession,
    case: Case,
    *,
    actor_user_id: UUID | None = None,
) -> None:
    metadata = case.metadata_json or {}
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="case.created",
        target_type="case",
        target_id=str(case.id),
        metadata={
            "root_entity_id": metadata.get("root_entity_id"),
            "risk_level": case.risk_level,
            "status": case.status,
        },
    )


async def write_case_reused_audit_log(
    db: AsyncSession,
    case: Case,
    *,
    actor_user_id: UUID | None = None,
) -> None:
    metadata = case.metadata_json or {}
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="case.reused",
        target_type="case",
        target_id=str(case.id),
        metadata={
            "root_entity_id": metadata.get("root_entity_id"),
            "status": case.status,
        },
    )


async def write_case_synced_audit_log(
    db: AsyncSession,
    case: Case,
    *,
    snapshot: dict,
    actor_user_id: UUID | None = None,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="case.synced",
        target_type="case",
        target_id=str(case.id),
        metadata={"snapshot": snapshot},
    )


async def write_case_status_changed_audit_log(
    db: AsyncSession,
    case: Case,
    *,
    old_status: str,
    new_status: CaseStatus,
    reason: str,
    actor_user_id: UUID | None = None,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="case.status_changed",
        target_type="case",
        target_id=str(case.id),
        metadata={
            "old_status": old_status,
            "new_status": new_status.value,
            "reason": reason,
        },
    )
