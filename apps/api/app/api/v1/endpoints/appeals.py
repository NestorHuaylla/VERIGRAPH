from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_report_reviewer
from app.db.session import get_db
from app.models.user import User
from app.schemas.appeal import AppealResponse, AppealStatusResponse, AppealStatusUpdate
from app.services.appeals import AppealNotFoundError
from app.services.appeals import update_appeal_status as update_appeal_status_service

router = APIRouter()


@router.patch("/{appeal_id}/status", response_model=AppealStatusResponse)
async def update_appeal_status(
    appeal_id: UUID,
    payload: AppealStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_report_reviewer),
) -> AppealStatusResponse:
    try:
        appeal: AppealResponse = await update_appeal_status_service(db, appeal_id, payload, actor_user_id=current_user.id)
    except AppealNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appeal not found.") from exc

    return AppealStatusResponse(
        id=appeal.id,
        report_id=appeal.report_id,
        status=appeal.status,
        message="Estado de apelacion actualizado.",
    )
