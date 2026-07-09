from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ReviewStatus
from app.core.dependencies import require_report_reviewer, require_reporter_or_reviewer, require_worker_or_report_reviewer
from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_db
from app.models.user import User
from app.schemas.audit import AuditLogResponse
from app.schemas.appeal import AppealCreate, AppealResponse
from app.schemas.evidence import EvidenceCreate, EvidenceResponse
from app.schemas.report import (
    ReportCreate,
    ReportDetailResponse,
    ReportListItem,
    ReportResponse,
    ReportStatusResponse,
    ReportStatusUpdate,
)
from app.services.audit import list_report_audit_logs as list_report_audit_logs_service
from app.services.appeals import create_report_appeal as create_report_appeal_service
from app.services.appeals import list_report_appeals as list_report_appeals_service
from app.services.abuse import AbuseValidationError, build_public_report_request_metadata
from app.services.evidence import create_report_evidence as create_report_evidence_service
from app.services.evidence import create_report_evidence_from_upload as create_report_evidence_from_upload_service
from app.services.evidence import build_evidence_response
from app.services.evidence import list_report_evidence as list_report_evidence_service
from app.services.evidence_analysis import EvidenceAnalysisError, process_report_evidence_analysis
from app.services.reports import ReportNotFoundError
from app.services.reports import create_report as create_report_service
from app.services.reports import find_report_by_id
from app.services.reports import get_report_detail as get_report_detail_service
from app.services.reports import list_reports as list_reports_service
from app.services.reports import update_report_status as update_report_status_service
from app.services.storage import EvidenceStorageError

router = APIRouter()


@router.get("", response_model=list[ReportListItem])
async def list_reports(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[ReportListItem]:
    return await list_reports_service(db, limit=limit, offset=offset)


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def get_report_detail(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> ReportDetailResponse:
    try:
        return await get_report_detail_service(db, report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc


@router.get("/{report_id}/audit-logs", response_model=list[AuditLogResponse])
async def list_report_audit_logs(
    report_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[AuditLogResponse]:
    report = await find_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    return await list_report_audit_logs_service(db, report_id, limit=limit, offset=offset)


@router.get("/{report_id}/appeals", response_model=list[AppealResponse])
async def list_report_appeals(
    report_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[AppealResponse]:
    try:
        return await list_report_appeals_service(db, report_id, limit=limit, offset=offset)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc


@router.post("/{report_id}/appeals", response_model=AppealResponse, status_code=status.HTTP_201_CREATED)
async def create_report_appeal(
    report_id: UUID,
    payload: AppealCreate,
    db: AsyncSession = Depends(get_db),
) -> AppealResponse:
    try:
        return await create_report_appeal_service(db, report_id, payload)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc


@router.get("/{report_id}/evidence", response_model=list[EvidenceResponse])
async def list_report_evidence(
    report_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[EvidenceResponse]:
    try:
        return await list_report_evidence_service(db, report_id, limit=limit, offset=offset)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc


@router.post("/{report_id}/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def create_report_evidence(
    report_id: UUID,
    payload: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_reporter_or_reviewer),
) -> EvidenceResponse:
    try:
        return await create_report_evidence_service(db, report_id, payload, actor_user_id=current_user.id)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc


@router.post("/{report_id}/evidence/upload", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def upload_report_evidence(
    report_id: UUID,
    file: UploadFile = File(...),
    description: str | None = Form(default=None, max_length=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_reporter_or_reviewer),
) -> EvidenceResponse:
    try:
        return await create_report_evidence_from_upload_service(
            db,
            report_id,
            file,
            description=description,
            actor_user_id=current_user.id,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc
    except EvidenceStorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{report_id}/evidence/{evidence_id}/analyze", response_model=EvidenceResponse)
async def analyze_report_evidence(
    report_id: UUID,
    evidence_id: UUID,
    prefer_ai: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: User | None = Depends(require_worker_or_report_reviewer),
) -> EvidenceResponse:
    try:
        evidence = await process_report_evidence_analysis(
            db,
            report_id=report_id,
            evidence_id=evidence_id,
            prefer_ai=prefer_ai,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc
    except EvidenceAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return build_evidence_response(evidence)


@router.patch("/{report_id}/status", response_model=ReportStatusResponse)
async def update_report_status(
    report_id: UUID,
    payload: ReportStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_report_reviewer),
) -> ReportStatusResponse:
    try:
        report = await update_report_status_service(db, report_id, payload, actor_user_id=current_user.id)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.") from exc

    return ReportStatusResponse(
        id=str(report.id),
        status=ReviewStatus(report.status),
        message="Estado de reporte actualizado.",
    )


@router.post("", response_model=ReportResponse)
async def create_report(
    payload: ReportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(enforce_rate_limit),
) -> ReportResponse:
    try:
        result = await create_report_service(
            db,
            payload,
            request_metadata=build_public_report_request_metadata(request),
        )
    except AbuseValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.signal.message) from exc

    return ReportResponse(
        id=str(result.report.id),
        entity_id=str(result.entity.id),
        status=result.report.status,
        risk_score=result.risk.score,
        risk_level=result.risk.level,
        message=f"Reporte recibido. Score inicial {result.risk.score} ({result.risk.level.value}).",
    )
