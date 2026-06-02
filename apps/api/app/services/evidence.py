from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.evidence import EvidenceFile
from app.schemas.evidence import EvidenceCreate, EvidenceResponse
from app.services.audit import write_audit_log
from app.services.evidence_analysis import build_evidence_analysis_metadata
from app.services.reports import ReportNotFoundError, find_report_by_id
from app.services.storage import StoredUpload, store_evidence_upload


DEFAULT_EVIDENCE_LIMIT = 100


async def create_report_evidence(
    db: AsyncSession,
    report_id: UUID,
    payload: EvidenceCreate,
    *,
    actor_user_id: UUID | None = None,
) -> EvidenceResponse:
    report = await find_report_by_id(db, report_id)
    if report is None:
        raise ReportNotFoundError(report_id)

    return await persist_report_evidence(db, report_id, payload, actor_user_id=actor_user_id)


async def create_report_evidence_from_upload(
    db: AsyncSession,
    report_id: UUID,
    upload_file: UploadFile,
    *,
    description: str | None = None,
    actor_user_id: UUID | None = None,
) -> EvidenceResponse:
    report = await find_report_by_id(db, report_id)
    if report is None:
        raise ReportNotFoundError(report_id)

    stored_upload = await store_evidence_upload(upload_file, report_id=report_id)
    payload = build_evidence_create_from_stored_upload(stored_upload, description=description)
    return await persist_report_evidence(db, report_id, payload, actor_user_id=actor_user_id)


async def persist_report_evidence(
    db: AsyncSession,
    report_id: UUID,
    payload: EvidenceCreate,
    *,
    actor_user_id: UUID | None = None,
) -> EvidenceResponse:
    evidence = build_evidence_file(report_id, payload)
    db.add(evidence)
    await db.flush()
    await write_evidence_added_audit_log(db, evidence, actor_user_id=actor_user_id)

    await db.commit()
    await db.refresh(evidence)

    return build_evidence_response(evidence)


async def list_report_evidence(
    db: AsyncSession,
    report_id: UUID,
    *,
    limit: int = DEFAULT_EVIDENCE_LIMIT,
    offset: int = 0,
) -> list[EvidenceResponse]:
    report = await find_report_by_id(db, report_id)
    if report is None:
        raise ReportNotFoundError(report_id)

    result = await db.execute(
        select(EvidenceFile)
        .where(EvidenceFile.report_id == report_id)
        .order_by(EvidenceFile.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return [build_evidence_response(evidence) for evidence in result.scalars().all()]


def build_evidence_file(report_id: UUID, payload: EvidenceCreate) -> EvidenceFile:
    metadata = dict(payload.metadata or {})
    metadata["size_bytes"] = payload.size_bytes
    metadata["description"] = payload.description
    metadata.setdefault("storage_status", "registered")

    return EvidenceFile(
        report_id=report_id,
        object_key=payload.object_key or build_default_object_key(report_id, payload),
        filename=payload.filename,
        content_type=payload.content_type,
        sha256=payload.sha256,
        metadata_json=metadata,
    )


def build_evidence_response(evidence: EvidenceFile) -> EvidenceResponse:
    metadata = dict(evidence.metadata_json or {})
    return EvidenceResponse(
        id=str(evidence.id),
        report_id=str(evidence.report_id),
        object_key=evidence.object_key,
        filename=evidence.filename,
        content_type=evidence.content_type,
        size_bytes=metadata.get("size_bytes"),
        sha256=evidence.sha256,
        metadata=metadata,
        created_at=evidence.created_at,
    )


def build_default_object_key(report_id: UUID, payload: EvidenceCreate) -> str:
    extension = Path(payload.filename).suffix.lower()
    return f"reports/{report_id}/evidence/{payload.sha256}{extension}"


def build_evidence_create_from_stored_upload(stored_upload: StoredUpload, *, description: str | None = None) -> EvidenceCreate:
    metadata = {
        "storage_status": "stored",
        "storage_backend": stored_upload.storage_backend,
    }
    if stored_upload.path is not None:
        metadata["local_path"] = str(stored_upload.path)
    if stored_upload.bucket:
        metadata["s3_bucket"] = stored_upload.bucket
        metadata["s3_endpoint"] = settings.s3_endpoint
    if stored_upload.exif is not None:
        metadata["exif"] = {
            "status": stored_upload.exif.status,
            "metadata_removed": stored_upload.exif.metadata_removed,
            "original_size_bytes": stored_upload.exif.original_size_bytes,
            "stripped_size_bytes": stored_upload.exif.stripped_size_bytes,
        }
    metadata.update(build_evidence_analysis_metadata(stored_upload.content_type))

    return EvidenceCreate(
        filename=stored_upload.filename,
        content_type=stored_upload.content_type,
        size_bytes=stored_upload.size_bytes,
        sha256=stored_upload.sha256,
        object_key=stored_upload.object_key,
        description=description,
        metadata=metadata,
    )


async def write_evidence_added_audit_log(
    db: AsyncSession,
    evidence: EvidenceFile,
    *,
    actor_user_id: UUID | None = None,
) -> None:
    metadata = dict(evidence.metadata_json or {})
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="report.evidence_added",
        target_type="report",
        target_id=str(evidence.report_id),
        metadata={
            "evidence_id": str(evidence.id),
            "filename": evidence.filename,
            "content_type": evidence.content_type,
            "sha256": evidence.sha256,
            "object_key": evidence.object_key,
            "size_bytes": metadata.get("size_bytes"),
        },
    )
