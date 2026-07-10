import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.entity import Entity, EntityRelation
from app.models.evidence import EvidenceFile
from app.models.notification import Notification, NotificationDelivery
from app.models.report import Report
from app.services.ai_vision import VisionOutcome
from app.services.ocr import OcrOutcome
from app.services.evidence_analysis import (
    AiVisionExtractor,
    OcrExtractor,
    PlainTextExtractor,
    build_evidence_analysis_metadata,
    get_text_extractor,
    process_report_evidence_analysis,
)


class FakeScalarResult:
    def __init__(self, result: object | None) -> None:
        self.result = result

    def scalar_one_or_none(self) -> object | None:
        return self.result


class FakeRowResult:
    def __init__(self, row: object | None) -> None:
        self.row = row

    def one_or_none(self) -> object | None:
        return self.row


class FakeAnalysisSession:
    def __init__(self, execute_results: list[object | None]) -> None:
        self.execute_results = execute_results
        self.objects: list[object] = []
        self.committed = False
        self.refreshed: object | None = None

    async def execute(self, _: Any) -> object:
        result = self.execute_results.pop(0)
        if isinstance(result, tuple):
            return FakeRowResult(result)
        return FakeScalarResult(result)

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def flush(self) -> None:
        for obj in self.objects:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        self.refreshed = obj

    def begin_nested(self) -> "FakeNestedTransaction":
        return FakeNestedTransaction(self)


class FakeNestedTransaction:
    def __init__(self, session: FakeAnalysisSession) -> None:
        self.session = session

    async def __aenter__(self) -> "FakeNestedTransaction":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False


def make_entity(entity_type: str, normalized_value: str) -> Entity:
    entity = Entity(
        type=entity_type,
        raw_value=normalized_value,
        normalized_value=normalized_value,
        display_value=normalized_value,
        metadata_json={},
    )
    entity.id = uuid4()
    return entity


def make_report(source_entity: Entity) -> Report:
    report = Report(
        entity_id=source_entity.id,
        reporter_contact=None,
        reason="Reporte base.",
        status="pending",
        source="public_form",
        metadata_json={},
    )
    report.id = uuid4()
    report.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return report


def make_evidence(report_id, local_path: Path, *, content_type: str = "text/plain") -> EvidenceFile:
    evidence = EvidenceFile(
        report_id=report_id,
        object_key=f"reports/{report_id}/evidence/test.txt",
        filename="evidencia.txt",
        content_type=content_type,
        sha256="a" * 64,
        metadata_json={
            "local_path": str(local_path),
            "analysis": {
                "status": "queued",
                "engine": "plain_text",
                "provider": "local",
                "relation_type": "mentioned_in_evidence",
            },
        },
    )
    evidence.id = uuid4()
    evidence.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return evidence


def test_get_text_extractor_selects_plain_text() -> None:
    assert isinstance(get_text_extractor("text/plain"), PlainTextExtractor)


def test_get_text_extractor_selects_ocr_by_default() -> None:
    assert isinstance(get_text_extractor("image/png"), OcrExtractor)


def test_get_text_extractor_selects_ai_vision_when_requested() -> None:
    assert isinstance(get_text_extractor("image/png", prefer_ai=True), AiVisionExtractor)


def test_build_evidence_analysis_metadata_prepares_ai_provider() -> None:
    metadata = build_evidence_analysis_metadata("image/png", prefer_ai=True)

    assert metadata["analysis"]["status"] == "queued"
    assert metadata["analysis"]["engine"] == "ai_vision"
    assert metadata["analysis"]["provider"] == "claude_vision"
    assert metadata["analysis"]["relation_type"] == "mentioned_in_evidence"


def make_image_evidence(report_id, local_path: Path, *, content_type: str = "image/png") -> EvidenceFile:
    evidence = EvidenceFile(
        report_id=report_id,
        object_key=f"reports/{report_id}/evidence/test.png",
        filename="evidencia.png",
        content_type=content_type,
        sha256="b" * 64,
        metadata_json={"local_path": str(local_path)},
    )
    evidence.id = uuid4()
    evidence.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return evidence


def test_ocr_extractor_uses_tesseract_when_reliable(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "evidencia.png"
    path.write_bytes(b"fake-image-bytes")
    evidence = make_image_evidence(uuid4(), path)

    monkeypatch.setattr(
        "app.services.evidence_analysis.run_tesseract_ocr",
        lambda file_bytes, lang: OcrOutcome(text="Contacto +51 999 999 999", confidence=92.0),
    )

    extraction = asyncio.run(OcrExtractor().extract(evidence))

    assert extraction.status == "completed"
    assert extraction.engine == "ocr"
    assert extraction.provider == "tesseract"
    assert extraction.extracted_text == "Contacto +51 999 999 999"


def test_ocr_extractor_falls_back_to_ai_vision_when_unreliable(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "evidencia.png"
    path.write_bytes(b"fake-image-bytes")
    evidence = make_image_evidence(uuid4(), path)

    monkeypatch.setattr(
        "app.services.evidence_analysis.run_tesseract_ocr",
        lambda file_bytes, lang: OcrOutcome(text="a", confidence=10.0),
    )
    monkeypatch.setattr(
        "app.services.evidence_analysis.run_claude_vision_ocr",
        lambda file_bytes, *, content_type, api_key, model: VisionOutcome(
            text="Contacto +51 999 999 999", model=model
        ),
    )

    extraction = asyncio.run(OcrExtractor().extract(evidence))

    assert extraction.status == "completed"
    assert extraction.engine == "ai_vision"
    assert extraction.provider == "claude_vision"
    assert extraction.extracted_text == "Contacto +51 999 999 999"


def test_ocr_extractor_routes_pdf_directly_to_ai_vision(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "evidencia.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    evidence = make_image_evidence(uuid4(), path, content_type="application/pdf")

    called = {"tesseract": False}

    def fail_if_called(*args, **kwargs):
        called["tesseract"] = True
        raise AssertionError("Tesseract no deberia llamarse para PDFs")

    monkeypatch.setattr("app.services.evidence_analysis.run_tesseract_ocr", fail_if_called)
    monkeypatch.setattr(
        "app.services.evidence_analysis.run_claude_vision_ocr",
        lambda file_bytes, *, content_type, api_key, model: VisionOutcome(
            text="Texto del PDF", model=model
        ),
    )

    extraction = asyncio.run(OcrExtractor().extract(evidence))

    assert called["tesseract"] is False
    assert extraction.status == "completed"
    assert extraction.engine == "ai_vision"
    assert extraction.extracted_text == "Texto del PDF"


def test_ai_vision_extractor_calls_claude_vision_directly(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "evidencia.png"
    path.write_bytes(b"fake-image-bytes")
    evidence = make_image_evidence(uuid4(), path)

    monkeypatch.setattr(
        "app.services.evidence_analysis.run_claude_vision_ocr",
        lambda file_bytes, *, content_type, api_key, model: VisionOutcome(
            text="Contacto +51 999 999 999", model=model
        ),
    )

    extraction = asyncio.run(AiVisionExtractor().extract(evidence))

    assert extraction.status == "completed"
    assert extraction.engine == "ai_vision"
    assert extraction.provider == "claude_vision"
    assert extraction.extracted_text == "Contacto +51 999 999 999"


def test_ai_vision_extractor_reports_failure_when_no_text_found(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "evidencia.png"
    path.write_bytes(b"fake-image-bytes")
    evidence = make_image_evidence(uuid4(), path)

    monkeypatch.setattr(
        "app.services.evidence_analysis.run_claude_vision_ocr",
        lambda file_bytes, *, content_type, api_key, model: VisionOutcome(text="", model=model),
    )

    extraction = asyncio.run(AiVisionExtractor().extract(evidence))

    assert extraction.status == "failed"
    assert extraction.error is not None


def test_plain_text_extractor_reads_local_file(tmp_path: Path) -> None:
    path = tmp_path / "evidencia.txt"
    path.write_text("Contacto +51 999 999 999", encoding="utf-8")
    evidence = make_evidence(uuid4(), path)

    extraction = asyncio.run(PlainTextExtractor().extract(evidence))

    assert extraction.status == "completed"
    assert extraction.engine == "plain_text"
    assert extraction.provider == "local"
    assert extraction.extracted_text == "Contacto +51 999 999 999"


def test_plain_text_extractor_reads_s3_file(monkeypatch) -> None:
    evidence = make_evidence(uuid4(), Path("unused.txt"))
    evidence.metadata_json["storage_backend"] = "s3"
    evidence.metadata_json.pop("local_path")
    monkeypatch.setattr("app.services.evidence_analysis.read_s3_object_text", lambda object_key: "Contacto +51 999 999 999")

    extraction = asyncio.run(PlainTextExtractor().extract(evidence))

    assert extraction.status == "completed"
    assert extraction.extracted_text == "Contacto +51 999 999 999"


def test_process_report_evidence_analysis_creates_relation_from_text(tmp_path: Path) -> None:
    path = tmp_path / "evidencia.txt"
    path.write_text("Contacto +51 999 999 999", encoding="utf-8")
    source = make_entity("url", "https://estafa-peru.com")
    target = make_entity("phone", "+51999999999")
    report = make_report(source)
    evidence = make_evidence(report.id, path)
    session = FakeAnalysisSession([evidence, (report, source), target, None])

    analyzed = asyncio.run(
        process_report_evidence_analysis(
            session,  # type: ignore[arg-type]
            report_id=report.id,
            evidence_id=evidence.id,
        )
    )

    assert analyzed is evidence
    assert session.committed is True
    assert session.refreshed is evidence
    assert len(session.objects) == 3
    relation = session.objects[0]
    notification = session.objects[1]
    delivery = session.objects[2]
    assert isinstance(relation, EntityRelation)
    assert relation.relation_type == "mentioned_in_evidence"
    assert relation.evidence["evidence_id"] == str(evidence.id)
    assert relation.evidence["source"] == "evidence_analysis"
    assert evidence.metadata_json["analysis"]["status"] == "completed"
    assert evidence.metadata_json["analysis"]["engine"] == "plain_text"
    assert evidence.metadata_json["analysis"]["relations_created"] == 1
    assert evidence.metadata_json["analysis"]["extracted_text"] == "Contacto +51 999 999 999"
    assert isinstance(notification, Notification)
    assert notification.event_type == "evidence.analysis_completed"
    assert notification.metadata_json["report_id"] == str(report.id)
    assert notification.metadata_json["evidence_id"] == str(evidence.id)
    assert notification.metadata_json["relations_created"] == 1
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.notification_id == notification.id
    assert delivery.channel == "webhook"
    assert delivery.status == "pending"
