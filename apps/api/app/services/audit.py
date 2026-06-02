from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.schemas.audit import AuditLogResponse


DEFAULT_AUDIT_LOG_LIMIT = 100


async def write_audit_log(
    db: AsyncSession,
    *,
    actor_user_id: UUID | None,
    action: str,
    target_type: str,
    target_id: str,
    metadata: dict | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_json=metadata or {},
    )
    db.add(audit_log)
    return audit_log


async def list_report_audit_logs(
    db: AsyncSession,
    report_id: UUID,
    *,
    limit: int = DEFAULT_AUDIT_LOG_LIMIT,
    offset: int = 0,
) -> list[AuditLogResponse]:
    return await list_audit_logs_for_target(
        db,
        target_type="report",
        target_id=str(report_id),
        limit=limit,
        offset=offset,
    )


async def list_audit_logs_for_target(
    db: AsyncSession,
    *,
    target_type: str,
    target_id: str,
    limit: int = DEFAULT_AUDIT_LOG_LIMIT,
    offset: int = 0,
) -> list[AuditLogResponse]:
    statement = (
        select(AuditLog)
        .where(AuditLog.target_type == target_type, AuditLog.target_id == target_id)
        .order_by(AuditLog.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(statement)
    return [build_audit_log_response(audit_log) for audit_log in result.scalars().all()]


def build_audit_log_response(audit_log: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=str(audit_log.id),
        actor_user_id=str(audit_log.actor_user_id) if audit_log.actor_user_id else None,
        action=audit_log.action,
        target_type=audit_log.target_type,
        target_id=audit_log.target_id,
        metadata=audit_log.metadata_json or {},
        created_at=audit_log.created_at,
    )
