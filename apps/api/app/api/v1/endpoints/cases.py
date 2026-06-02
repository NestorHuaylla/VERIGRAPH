from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CaseStatus
from app.core.dependencies import require_report_reviewer
from app.db.session import get_db
from app.models.user import User
from app.schemas.case import CaseDetailResponse, CaseListItem, CaseStatusResponse, CaseStatusUpdate, CaseSyncResponse
from app.services.cases import CaseNotFoundError
from app.services.cases import get_case_detail as get_case_detail_service
from app.services.cases import list_cases as list_cases_service
from app.services.cases import sync_case_snapshot as sync_case_snapshot_service
from app.services.cases import update_case_status as update_case_status_service

router = APIRouter()


@router.get("", response_model=list[CaseListItem])
async def list_cases(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[CaseListItem]:
    return await list_cases_service(db, limit=limit, offset=offset)


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case_detail(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> CaseDetailResponse:
    try:
        return await get_case_detail_service(db, case_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.") from exc


@router.patch("/{case_id}/status", response_model=CaseStatusResponse)
async def update_case_status(
    case_id: UUID,
    payload: CaseStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_report_reviewer),
) -> CaseStatusResponse:
    try:
        case = await update_case_status_service(db, case_id, payload, actor_user_id=current_user.id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.") from exc

    return CaseStatusResponse(
        id=str(case.id),
        status=CaseStatus(case.status),
        message="Estado de expediente actualizado.",
    )


@router.post("/{case_id}/sync", response_model=CaseSyncResponse)
async def sync_case_snapshot(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_report_reviewer),
) -> CaseSyncResponse:
    try:
        case = await sync_case_snapshot_service(db, case_id, actor_user_id=current_user.id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.") from exc

    return CaseSyncResponse(
        id=str(case.id),
        snapshot=(case.metadata_json or {}).get("snapshot", {}),
        message="Snapshot de expediente sincronizado.",
    )
