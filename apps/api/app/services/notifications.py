from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import NotificationSeverity, RiskLevel
from app.models.appeal import Appeal
from app.models.case import Case
from app.models.entity import Entity
from app.models.evidence import EvidenceFile
from app.models.external_reputation import ExternalReputationCheck
from app.models.notification import Notification
from app.models.report import Report
from app.schemas.external_reputation import ExternalReputationSummary
from app.schemas.notification import NotificationListItem
from app.services.notification_deliveries import create_default_notification_deliveries
from app.services.scoring import ScoreResult


DEFAULT_NOTIFICATION_LIMIT = 100
CASE_RISK_NOTIFICATION_LEVELS = {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}
REPORT_RISK_NOTIFICATION_LEVELS = {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}


class NotificationNotFoundError(Exception):
    def __init__(self, notification_id: UUID) -> None:
        super().__init__(f"Notification {notification_id} was not found.")
        self.notification_id = notification_id


async def create_notification(
    db: AsyncSession,
    *,
    event_type: str,
    title: str,
    message: str,
    severity: NotificationSeverity,
    metadata: dict | None = None,
    user_id: UUID | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        event_type=event_type,
        title=title,
        message=message,
        severity=severity.value,
        is_read=False,
        metadata_json=metadata or {},
    )
    db.add(notification)
    return notification


async def list_notifications(
    db: AsyncSession,
    *,
    unread_only: bool = False,
    limit: int = DEFAULT_NOTIFICATION_LIMIT,
    offset: int = 0,
) -> list[NotificationListItem]:
    statement = select(Notification).order_by(desc(Notification.created_at)).limit(limit).offset(offset)
    if unread_only:
        statement = statement.where(Notification.is_read.is_(False))

    result = await db.execute(statement)
    return [build_notification_list_item(notification) for notification in result.scalars().all()]


async def mark_notification_read(db: AsyncSession, notification_id: UUID) -> Notification:
    notification = await find_notification_by_id(db, notification_id)
    if notification is None:
        raise NotificationNotFoundError(notification_id)

    notification.is_read = True
    await db.commit()
    await db.refresh(notification)

    return notification


async def find_notification_by_id(db: AsyncSession, notification_id: UUID) -> Notification | None:
    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    return result.scalar_one_or_none()


async def create_case_risk_notification(
    db: AsyncSession,
    case: Case,
    *,
    snapshot: dict,
    previous_snapshot: dict | None = None,
) -> Notification | None:
    risk_level = str(snapshot.get("case_risk_level") or case.risk_level)
    previous_risk_level = str((previous_snapshot or {}).get("case_risk_level") or "")
    if risk_level not in CASE_RISK_NOTIFICATION_LEVELS:
        return None
    if previous_risk_level == risk_level:
        return None

    severity = NotificationSeverity.CRITICAL if risk_level == RiskLevel.CRITICAL.value else NotificationSeverity.WARNING
    event_type = "case.critical" if risk_level == RiskLevel.CRITICAL.value else "case.high_risk"
    case_score = snapshot.get("case_score")
    root_entity_id = (case.metadata_json or {}).get("root_entity_id")

    notification = await create_notification(
        db,
        event_type=event_type,
        title=build_case_risk_notification_title(risk_level),
        message=build_case_risk_notification_message(case, risk_level=risk_level, case_score=case_score),
        severity=severity,
        metadata={
            "case_id": str(case.id),
            "case_title": case.title,
            "risk_level": risk_level,
            "case_score": case_score,
            "root_entity_id": root_entity_id,
            "reports_count": snapshot.get("reports_count", 0),
            "evidence_count": snapshot.get("evidence_count", 0),
            "relations_count": snapshot.get("relations_count", snapshot.get("graph_edges_count", 0)),
        },
    )
    await create_default_notification_deliveries(db, notification)
    return notification


async def create_report_risk_notification(
    db: AsyncSession,
    *,
    report: Report,
    entity: Entity,
    risk: ScoreResult,
    relations_created: int,
    graph_degree: int,
) -> Notification | None:
    if risk.level.value not in REPORT_RISK_NOTIFICATION_LEVELS:
        return None

    severity = NotificationSeverity.CRITICAL if risk.level == RiskLevel.CRITICAL else NotificationSeverity.WARNING
    event_type = "report.critical" if risk.level == RiskLevel.CRITICAL else "report.high_risk"

    notification = await create_notification(
        db,
        event_type=event_type,
        title=build_report_risk_notification_title(risk.level),
        message=build_report_risk_notification_message(report, risk),
        severity=severity,
        metadata={
            "report_id": str(report.id),
            "entity_id": str(entity.id),
            "entity_type": entity.type,
            "entity_value": entity.display_value,
            "entity_normalized_value": entity.normalized_value,
            "risk_score": risk.score,
            "risk_level": risk.level.value,
            "relations_created": relations_created,
            "graph_degree": graph_degree,
            "source": report.source,
        },
    )
    await create_default_notification_deliveries(db, notification)
    return notification


async def create_appeal_created_notification(db: AsyncSession, appeal: Appeal) -> Notification:
    notification = await create_notification(
        db,
        event_type="appeal.created",
        title="Apelacion pendiente de revision",
        message=f"El reporte {appeal.report_id} recibio una apelacion pendiente.",
        severity=NotificationSeverity.WARNING,
        metadata={
            "appeal_id": str(appeal.id),
            "report_id": str(appeal.report_id),
            "appeal_status": appeal.status,
            "has_appellant_contact": bool(appeal.appellant_contact),
        },
    )
    await create_default_notification_deliveries(db, notification)
    return notification


async def create_evidence_analysis_notification(
    db: AsyncSession,
    *,
    evidence: EvidenceFile,
    report: Report,
    analysis: dict,
) -> Notification | None:
    entities_created = int(analysis.get("entities_created") or 0)
    relations_created = int(analysis.get("relations_created") or 0)
    if analysis.get("status") != "completed":
        return None
    if entities_created == 0 and relations_created == 0:
        return None

    notification = await create_notification(
        db,
        event_type="evidence.analysis_completed",
        title="Evidencia conecto nuevas entidades",
        message=(
            f"La evidencia {evidence.filename} agrego {relations_created} relaciones "
            f"al reporte {report.id}."
        ),
        severity=NotificationSeverity.WARNING,
        metadata={
            "report_id": str(report.id),
            "evidence_id": str(evidence.id),
            "filename": evidence.filename,
            "content_type": evidence.content_type,
            "entities_created": entities_created,
            "relations_created": relations_created,
            "engine": analysis.get("engine"),
            "provider": analysis.get("provider"),
            "relation_type": analysis.get("relation_type"),
        },
    )
    await create_default_notification_deliveries(db, notification)
    return notification


async def create_external_reputation_notification(
    db: AsyncSession,
    *,
    entity: Entity,
    checks: list[ExternalReputationCheck],
    summary: ExternalReputationSummary,
) -> Notification | None:
    if not summary.malicious:
        return None

    severity = NotificationSeverity.CRITICAL if summary.highest_severity == "critical" else NotificationSeverity.WARNING
    malicious_sources = ", ".join(summary.malicious_sources)
    notification = await create_notification(
        db,
        event_type="external_reputation.malicious",
        title="Reputacion externa maliciosa detectada",
        message=f"La entidad {entity.display_value} fue marcada como maliciosa por {malicious_sources}.",
        severity=severity,
        metadata={
            "entity_id": str(entity.id),
            "entity_type": entity.type,
            "entity_value": entity.display_value,
            "entity_normalized_value": entity.normalized_value,
            "malicious_sources": summary.malicious_sources,
            "checked_sources": summary.checked_sources,
            "highest_severity": summary.highest_severity,
            "checks": [
                {
                    "source": check.source,
                    "status": check.status,
                    "severity": check.severity,
                    "summary": check.summary,
                    "reference": check.reference,
                }
                for check in checks
                if check.malicious
            ],
        },
    )
    await create_default_notification_deliveries(db, notification)
    return notification


def build_case_risk_notification_title(risk_level: str) -> str:
    if risk_level == RiskLevel.CRITICAL.value:
        return "Expediente critico detectado"
    return "Expediente de alto riesgo detectado"


def build_case_risk_notification_message(case: Case, *, risk_level: str, case_score: object) -> str:
    score_fragment = f" con score {case_score}" if case_score is not None else ""
    return f"El expediente '{case.title}' quedo en nivel {risk_level}{score_fragment}."


def build_report_risk_notification_title(risk_level: RiskLevel) -> str:
    if risk_level == RiskLevel.CRITICAL:
        return "Reporte critico recibido"
    return "Reporte de alto riesgo recibido"


def build_report_risk_notification_message(report: Report, risk: ScoreResult) -> str:
    return f"El reporte {report.id} quedo en nivel {risk.level.value} con score {risk.score}."


def build_notification_list_item(notification: Notification) -> NotificationListItem:
    return NotificationListItem(
        id=str(notification.id),
        user_id=str(notification.user_id) if notification.user_id else None,
        event_type=notification.event_type,
        title=notification.title,
        message=notification.message,
        severity=NotificationSeverity(notification.severity),
        is_read=notification.is_read,
        metadata=notification.metadata_json or {},
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )
