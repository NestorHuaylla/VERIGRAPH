from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.evidence import EvidenceFile
from app.models.report import Report
from app.services.notifications import create_evidence_analysis_notification
from app.services.relations import create_entity_relations_from_text
from app.services.reports import ReportNotFoundError
from app.services.storage import EvidenceStorageError, read_s3_object_text


OCR_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

TEXT_CONTENT_TYPES = frozenset({"text/plain"})
MENTIONED_IN_EVIDENCE = "mentioned_in_evidence"
MAX_EXTRACTED_TEXT_CHARS = 20_000


class EvidenceAnalysisError(Exception):
    pass


class EvidenceNotFoundError(EvidenceAnalysisError):
    def __init__(self, evidence_id: UUID) -> None:
        super().__init__(f"Evidence {evidence_id} was not found.")
        self.evidence_id = evidence_id


class EvidenceReportMismatchError(EvidenceAnalysisError):
    def __init__(self, evidence_id: UUID, report_id: UUID) -> None:
        super().__init__(f"Evidence {evidence_id} does not belong to report {report_id}.")
        self.evidence_id = evidence_id
        self.report_id = report_id


@dataclass(frozen=True)
class EvidenceTextExtraction:
    status: str
    engine: str | None
    provider: str | None
    extracted_text: str | None = None
    error: str | None = None


class EvidenceTextExtractor:
    engine: str | None = None
    provider: str | None = None

    async def extract(self, evidence: EvidenceFile) -> EvidenceTextExtraction:
        raise NotImplementedError


class PlainTextExtractor(EvidenceTextExtractor):
    engine = "plain_text"
    provider = "local"

    async def extract(self, evidence: EvidenceFile) -> EvidenceTextExtraction:
        metadata = evidence.metadata_json or {}
        if metadata.get("storage_backend") == "s3":
            try:
                text = read_s3_object_text(evidence.object_key)
            except EvidenceStorageError as exc:
                return EvidenceTextExtraction(
                    status="failed",
                    engine=self.engine,
                    provider=self.provider,
                    error=str(exc),
                )
            return EvidenceTextExtraction(
                status="completed",
                engine=self.engine,
                provider=self.provider,
                extracted_text=text[:MAX_EXTRACTED_TEXT_CHARS],
            )

        local_path = metadata.get("local_path")
        if not local_path:
            return EvidenceTextExtraction(
                status="failed",
                engine=self.engine,
                provider=self.provider,
                error="Evidence local path is missing.",
            )

        path = Path(local_path)
        if not path.exists():
            return EvidenceTextExtraction(
                status="failed",
                engine=self.engine,
                provider=self.provider,
                error="Evidence local path does not exist.",
            )

        text = path.read_text(encoding="utf-8", errors="replace")
        return EvidenceTextExtraction(
            status="completed",
            engine=self.engine,
            provider=self.provider,
            extracted_text=text[:MAX_EXTRACTED_TEXT_CHARS],
        )


class OcrExtractorStub(EvidenceTextExtractor):
    engine = "ocr"
    provider = "tesseract_stub"

    async def extract(self, evidence: EvidenceFile) -> EvidenceTextExtraction:
        return EvidenceTextExtraction(
            status="queued",
            engine=self.engine,
            provider=self.provider,
        )


class AiVisionExtractorStub(EvidenceTextExtractor):
    engine = "ai_vision"
    provider = "openai_stub"

    async def extract(self, evidence: EvidenceFile) -> EvidenceTextExtraction:
        return EvidenceTextExtraction(
            status="queued",
            engine=self.engine,
            provider=self.provider,
        )


class UnsupportedExtractor(EvidenceTextExtractor):
    async def extract(self, evidence: EvidenceFile) -> EvidenceTextExtraction:
        return EvidenceTextExtraction(
            status="not_supported",
            engine=None,
            provider=None,
        )


async def process_report_evidence_analysis(
    db: AsyncSession,
    *,
    report_id: UUID,
    evidence_id: UUID,
    prefer_ai: bool = False,
) -> EvidenceFile:
    evidence = await find_evidence_by_id(db, evidence_id)
    if evidence is None:
        raise EvidenceNotFoundError(evidence_id)
    if evidence.report_id != report_id:
        raise EvidenceReportMismatchError(evidence_id, report_id)

    report, source_entity = await load_report_source_entity(db, report_id)
    extraction = await get_text_extractor(evidence.content_type, prefer_ai=prefer_ai).extract(evidence)

    metadata = update_evidence_analysis_metadata(
        evidence.metadata_json,
        extraction=extraction,
        entities_created=0,
        relations_created=0,
    )

    if extraction.status == "completed" and extraction.extracted_text and source_entity is not None:
        relation_result = await create_entity_relations_from_text(
            db,
            source_entity=source_entity,
            report_id=report.id,
            text=extraction.extracted_text,
            relation_type=MENTIONED_IN_EVIDENCE,
            indicator_source="evidence_analysis",
            evidence_extra={
                "evidence_id": str(evidence.id),
                "object_key": evidence.object_key,
            },
        )
        metadata = update_evidence_analysis_metadata(
            metadata,
            extraction=extraction,
            entities_created=relation_result.entities_created,
            relations_created=len(relation_result.relations),
        )
    elif extraction.status == "completed" and source_entity is None:
        metadata = update_evidence_analysis_metadata(
            metadata,
            extraction=EvidenceTextExtraction(
                status="failed",
                engine=extraction.engine,
                provider=extraction.provider,
                extracted_text=extraction.extracted_text,
                error="Report source entity is missing.",
            ),
            entities_created=0,
            relations_created=0,
        )

    evidence.metadata_json = metadata
    await create_evidence_analysis_notification(
        db,
        evidence=evidence,
        report=report,
        analysis=metadata.get("analysis") or {},
    )
    await db.commit()
    await db.refresh(evidence)
    return evidence


async def find_evidence_by_id(db: AsyncSession, evidence_id: UUID) -> EvidenceFile | None:
    result = await db.execute(select(EvidenceFile).where(EvidenceFile.id == evidence_id))
    return result.scalar_one_or_none()


async def load_report_source_entity(db: AsyncSession, report_id: UUID) -> tuple[Report, Entity | None]:
    result = await db.execute(
        select(Report, Entity)
        .outerjoin(Entity, Report.entity_id == Entity.id)
        .where(Report.id == report_id)
    )
    row = result.one_or_none()
    if row is None:
        raise ReportNotFoundError(report_id)

    report, entity = row
    return report, entity


def get_text_extractor(content_type: str, *, prefer_ai: bool = False) -> EvidenceTextExtractor:
    normalized_content_type = content_type.lower()
    if normalized_content_type in TEXT_CONTENT_TYPES:
        return PlainTextExtractor()
    if normalized_content_type in OCR_CONTENT_TYPES and prefer_ai:
        return AiVisionExtractorStub()
    if normalized_content_type in OCR_CONTENT_TYPES:
        return OcrExtractorStub()
    return UnsupportedExtractor()


def build_evidence_analysis_metadata(content_type: str, *, prefer_ai: bool = False) -> dict:
    extractor = get_text_extractor(content_type, prefer_ai=prefer_ai)
    status = "queued" if extractor.engine else "not_supported"

    return {
        "analysis": {
            "status": status,
            "engine": extractor.engine,
            "provider": extractor.provider,
            "relation_type": MENTIONED_IN_EVIDENCE,
            "extracted_text": None,
            "error": None,
            "entities_created": 0,
            "relations_created": 0,
        }
    }


def update_evidence_analysis_metadata(
    metadata: dict | None,
    *,
    extraction: EvidenceTextExtraction,
    entities_created: int,
    relations_created: int,
) -> dict:
    updated = dict(metadata or {})
    updated["analysis"] = {
        "status": extraction.status,
        "engine": extraction.engine,
        "provider": extraction.provider,
        "relation_type": MENTIONED_IN_EVIDENCE,
        "extracted_text": extraction.extracted_text,
        "error": extraction.error,
        "entities_created": entities_created,
        "relations_created": relations_created,
    }
    return updated
