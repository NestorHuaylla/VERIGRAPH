from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AppealStatus, ReviewStatus
from app.models.appeal import Appeal
from app.models.report import Report
from app.schemas.appeal import AppealCreate, AppealResponse, AppealStatusUpdate
from app.services.audit import write_audit_log
from app.services.notifications import create_appeal_created_notification
from app.services.reports import ReportNotFoundError, find_report_by_id


DEFAULT_APPEAL_LIMIT = 100


class AppealNotFoundError(Exception):
    def __init__(self, appeal_id: UUID) -> None:
        super().__init__(f"Appeal {appeal_id} was not found.")
        self.appeal_id = appeal_id


async def create_report_appeal(
    db: AsyncSession,
    report_id: UUID,
    payload: AppealCreate,
    *,
    actor_user_id: UUID | None = None,
) -> AppealResponse:
    report = await find_report_by_id(db, report_id)
    if report is None:
        raise ReportNotFoundError(report_id)

    appeal = build_appeal(report_id, payload)
    db.add(appeal)
    mark_report_as_appealed(report)
    await db.flush()
    await write_appeal_created_audit_log(db, appeal, actor_user_id=actor_user_id)
    await create_appeal_created_notification(db, appeal)

    await db.commit()
    await db.refresh(appeal)

    return build_appeal_response(appeal)


async def list_report_appeals(
    db: AsyncSession,
    report_id: UUID,
    *,
    limit: int = DEFAULT_APPEAL_LIMIT,
    offset: int = 0,
) -> list[AppealResponse]:
    report = await find_report_by_id(db, report_id)
    if report is None:
        raise ReportNotFoundError(report_id)

    result = await db.execute(
        select(Appeal)
        .where(Appeal.report_id == report_id)
        .order_by(Appeal.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return [build_appeal_response(appeal) for appeal in result.scalars().all()]


async def find_appeal_by_id(db: AsyncSession, appeal_id: UUID) -> Appeal | None:
    result = await db.execute(select(Appeal).where(Appeal.id == appeal_id))
    return result.scalar_one_or_none()


async def update_appeal_status(
    db: AsyncSession,
    appeal_id: UUID,
    payload: AppealStatusUpdate,
    *,
    actor_user_id: UUID | None = None,
) -> AppealResponse:
    appeal = await find_appeal_by_id(db, appeal_id)
    if appeal is None:
        raise AppealNotFoundError(appeal_id)

    old_status, new_status = apply_appeal_status_update(appeal, payload)
    await write_appeal_status_changed_audit_log(
        db,
        appeal,
        old_status=old_status,
        new_status=new_status,
        reason=payload.reason,
        actor_user_id=actor_user_id,
    )

    await db.commit()
    await db.refresh(appeal)

    return build_appeal_response(appeal)


def build_appeal(report_id: UUID, payload: AppealCreate) -> Appeal:
    return Appeal(
        report_id=report_id,
        appellant_contact=payload.appellant_contact,
        reason=payload.reason,
        status=AppealStatus.PENDING.value,
        resolution_reason=None,
        metadata_json={"status_history": []},
    )


def mark_report_as_appealed(report: Report) -> None:
    metadata = dict(report.metadata_json or {})
    metadata["has_open_appeal"] = True
    report.status = ReviewStatus.APPEAL.value
    report.metadata_json = metadata


def apply_appeal_status_update(appeal: Appeal, payload: AppealStatusUpdate) -> tuple[str, AppealStatus]:
    old_status = appeal.status
    metadata = dict(appeal.metadata_json or {})
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

    appeal.status = payload.status.value
    appeal.resolution_reason = payload.reason
    appeal.metadata_json = metadata

    return old_status, payload.status


def build_appeal_response(appeal: Appeal) -> AppealResponse:
    return AppealResponse(
        id=str(appeal.id),
        report_id=str(appeal.report_id),
        appellant_contact=appeal.appellant_contact,
        reason=appeal.reason,
        status=AppealStatus(appeal.status),
        resolution_reason=appeal.resolution_reason,
        metadata=appeal.metadata_json or {},
        created_at=appeal.created_at,
        updated_at=appeal.updated_at,
    )


async def write_appeal_created_audit_log(
    db: AsyncSession,
    appeal: Appeal,
    *,
    actor_user_id: UUID | None = None,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="report.appeal_created",
        target_type="report",
        target_id=str(appeal.report_id),
        metadata={
            "appeal_id": str(appeal.id),
            "appeal_status": appeal.status,
            "has_appellant_contact": bool(appeal.appellant_contact),
        },
    )


async def write_appeal_status_changed_audit_log(
    db: AsyncSession,
    appeal: Appeal,
    *,
    old_status: str,
    new_status: AppealStatus,
    reason: str,
    actor_user_id: UUID | None = None,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="appeal.status_changed",
        target_type="appeal",
        target_id=str(appeal.id),
        metadata={
            "report_id": str(appeal.report_id),
            "old_status": old_status,
            "new_status": new_status.value,
            "reason": reason,
        },
    )
