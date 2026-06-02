import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.entity import Entity, EntityRelation
from app.models.evidence import EvidenceFile
from app.models.notification import Notification, NotificationDelivery
from app.models.report import Report
from app.services.evidence_analysis import (
    AiVisionExtractorStub,
    OcrExtractorStub,
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


def test_get_text_extractor_selects_ocr_stub_by_default() -> None:
    assert isinstance(get_text_extractor("image/png"), OcrExtractorStub)


def test_get_text_extractor_selects_ai_stub_when_requested() -> None:
    assert isinstance(get_text_extractor("image/png", prefer_ai=True), AiVisionExtractorStub)


def test_build_evidence_analysis_metadata_prepares_ai_provider() -> None:
    metadata = build_evidence_analysis_metadata("image/png", prefer_ai=True)

    assert metadata["analysis"]["status"] == "queued"
    assert metadata["analysis"]["engine"] == "ai_vision"
    assert metadata["analysis"]["provider"] == "openai_stub"
    assert metadata["analysis"]["relation_type"] == "mentioned_in_evidence"


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
