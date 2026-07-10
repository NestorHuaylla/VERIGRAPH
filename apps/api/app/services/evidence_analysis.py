from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entity import Entity
from app.models.evidence import EvidenceFile
from app.models.report import Report
from app.services.ai_vision import ClaudeVisionUnavailableError, run_claude_vision_ocr
from app.services.notifications import create_evidence_analysis_notification
from app.services.ocr import TesseractUnavailableError, is_ocr_result_reliable, run_tesseract_ocr
from app.services.relations import create_entity_relations_from_text
from app.services.reports import ReportNotFoundError
from app.services.storage import EvidenceStorageError, read_s3_object_bytes, read_s3_object_text

logger = logging.getLogger(__name__)


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


async def read_evidence_bytes(evidence: EvidenceFile) -> bytes:
    """Lee el contenido binario crudo de la evidencia, sin importar si
    esta en el filesystem local o en S3. Usado por OCR y AI Vision, que
    a diferencia de PlainTextExtractor necesitan los bytes originales
    (una imagen decodificada como UTF-8 quedaria corrupta)."""
    metadata = evidence.metadata_json or {}

    if metadata.get("storage_backend") == "s3":
        return await asyncio.to_thread(read_s3_object_bytes, evidence.object_key)

    local_path = metadata.get("local_path")
    if not local_path:
        raise EvidenceStorageError("Evidence local path is missing.")

    path = Path(local_path)
    if not path.exists():
        raise EvidenceStorageError("Evidence local path does not exist.")

    return await asyncio.to_thread(path.read_bytes)


async def run_ai_vision_extraction(
    file_bytes: bytes, *, content_type: str, engine: str
) -> EvidenceTextExtraction:
    """Corre AI Vision (Claude) sobre los bytes dados y arma el
    EvidenceTextExtraction resultante. Compartido por OcrExtractor
    (cuando hace fallback) y AiVisionExtractor (motor directo)."""
    provider = "claude_vision"
    try:
        outcome = await asyncio.to_thread(
            run_claude_vision_ocr,
            file_bytes,
            content_type=content_type,
            api_key=settings.anthropic_api_key,
            model=settings.claude_vision_model,
        )
    except ClaudeVisionUnavailableError as exc:
        logger.error("AI Vision no disponible: %s", exc)
        return EvidenceTextExtraction(
            status="failed", engine=engine, provider=provider, error=str(exc)
        )

    if outcome.error is not None:
        return EvidenceTextExtraction(
            status="failed", engine=engine, provider=provider, error=outcome.error
        )
    if not outcome.success:
        return EvidenceTextExtraction(
            status="failed",
            engine=engine,
            provider=provider,
            error="AI Vision no encontro texto legible en el archivo.",
        )
    return EvidenceTextExtraction(
        status="completed",
        engine=engine,
        provider=provider,
        extracted_text=outcome.text[:MAX_EXTRACTED_TEXT_CHARS],
    )


class OcrExtractor(EvidenceTextExtractor):
    """Motor primario para imagenes: Tesseract (local, rapido, gratis).

    Si Tesseract no logra un resultado confiable (poca confianza o muy
    poco texto extraido) hace fallback automatico a AI Vision. Los PDFs
    se mandan directo a AI Vision, ya que Tesseract no puede leerlos sin
    convertirlos antes a imagen.
    """

    engine = "ocr"
    provider = "tesseract"

    async def extract(self, evidence: EvidenceFile) -> EvidenceTextExtraction:
        try:
            file_bytes = await read_evidence_bytes(evidence)
        except EvidenceStorageError as exc:
            return EvidenceTextExtraction(
                status="failed", engine=self.engine, provider=self.provider, error=str(exc)
            )

        content_type = evidence.content_type.lower()

        if content_type == "application/pdf":
            return await run_ai_vision_extraction(
                file_bytes, content_type=content_type, engine="ai_vision"
            )

        try:
            outcome = await asyncio.to_thread(
                run_tesseract_ocr, file_bytes, lang=settings.ocr_language
            )
        except TesseractUnavailableError as exc:
            logger.error("Tesseract no disponible, escalando a AI Vision: %s", exc)
            return await run_ai_vision_extraction(
                file_bytes, content_type=content_type, engine="ai_vision"
            )

        if is_ocr_result_reliable(
            outcome,
            min_confidence=settings.ocr_min_confidence,
            min_word_count=settings.ocr_min_word_count,
        ):
            return EvidenceTextExtraction(
                status="completed",
                engine=self.engine,
                provider=self.provider,
                extracted_text=outcome.text[:MAX_EXTRACTED_TEXT_CHARS],
            )

        logger.info(
            "Tesseract no fue confiable (confianza=%.1f, palabras=%d). "
            "Escalando a AI Vision.",
            outcome.confidence,
            outcome.word_count,
        )
        return await run_ai_vision_extraction(
            file_bytes, content_type=content_type, engine="ai_vision"
        )


class AiVisionExtractor(EvidenceTextExtractor):
    """Motor directo a AI Vision (Claude), sin pasar por Tesseract.
    Se usa cuando el endpoint recibe `prefer_ai=true`."""

    engine = "ai_vision"
    provider = "claude_vision"

    async def extract(self, evidence: EvidenceFile) -> EvidenceTextExtraction:
        try:
            file_bytes = await read_evidence_bytes(evidence)
        except EvidenceStorageError as exc:
            return EvidenceTextExtraction(
                status="failed", engine=self.engine, provider=self.provider, error=str(exc)
            )

        return await run_ai_vision_extraction(
            file_bytes, content_type=evidence.content_type.lower(), engine=self.engine
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
        return AiVisionExtractor()
    if normalized_content_type in OCR_CONTENT_TYPES:
        return OcrExtractor()
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
