import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.evidence import EvidenceFile
from app.models.report import Report
from app.schemas.evidence import EvidenceCreate
from app.services.evidence import (
    build_evidence_create_from_stored_upload,
    build_default_object_key,
    build_evidence_file,
    create_report_evidence,
    create_report_evidence_from_upload,
    list_report_evidence,
)
from app.services.reports import ReportNotFoundError
from app.services.storage import StoredUpload
from app.services import storage


SHA256 = "a" * 64
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeScalarOneResult:
    def __init__(self, item: object | None) -> None:
        self.item = item

    def scalar_one_or_none(self) -> object | None:
        return self.item


class FakeScalarManyResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> "FakeScalarManyResult":
        return self

    def all(self) -> list[object]:
        return self.items


class FakeEvidenceSession:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.objects: list[object] = []
        self.committed = False
        self.refreshed: object | None = None

    async def execute(self, statement: object) -> object:
        self.statement = statement
        return self.results.pop(0)

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def flush(self) -> None:
        for obj in self.objects:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        self.refreshed = obj


class FakeUploadFile:
    def __init__(self, *, filename: str, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self.content = content
        self.cursor = 0
        self.closed = False

    async def read(self, size: int) -> bytes:
        if self.cursor >= len(self.content):
            return b""

        chunk = self.content[self.cursor : self.cursor + size]
        self.cursor += len(chunk)
        return chunk

    async def close(self) -> None:
        self.closed = True


def build_report() -> Report:
    report = Report(
        entity_id=None,
        reporter_contact=None,
        reason="Promete ganancia garantizada y pide deposito primero.",
        status="pending",
        source="public_form",
        metadata_json={},
    )
    report.id = uuid4()
    report.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return report


def build_payload(**overrides: object) -> EvidenceCreate:
    data = {
        "filename": "captura.png",
        "content_type": "image/png",
        "size_bytes": 2048,
        "sha256": SHA256,
        "description": "Captura del chat con solicitud de deposito.",
    }
    data.update(overrides)
    return EvidenceCreate(**data)


def test_evidence_create_rejects_path_like_filename() -> None:
    with pytest.raises(ValidationError):
        build_payload(filename="../captura.png")


def test_evidence_create_rejects_unsupported_content_type() -> None:
    with pytest.raises(ValidationError):
        build_payload(content_type="application/x-msdownload")


def test_build_evidence_file_generates_default_object_key() -> None:
    report_id = uuid4()
    payload = build_payload()

    evidence = build_evidence_file(report_id, payload)

    assert evidence.report_id == report_id
    assert evidence.filename == "captura.png"
    assert evidence.content_type == "image/png"
    assert evidence.sha256 == SHA256
    assert evidence.object_key == build_default_object_key(report_id, payload)
    assert evidence.metadata_json["size_bytes"] == 2048
    assert evidence.metadata_json["storage_status"] == "registered"


def test_build_evidence_create_from_stored_upload_marks_image_for_ocr(tmp_path) -> None:
    stored = StoredUpload(
        filename="captura.png",
        content_type="image/png",
        size_bytes=12,
        sha256=SHA256,
        object_key=f"reports/{uuid4()}/evidence/{SHA256}.png",
        storage_backend="local",
        path=tmp_path / "captura.png",
    )

    payload = build_evidence_create_from_stored_upload(stored, description="Captura de chat.")

    assert payload.filename == "captura.png"
    assert payload.content_type == "image/png"
    assert payload.size_bytes == 12
    assert payload.sha256 == SHA256
    assert payload.description == "Captura de chat."
    assert payload.metadata["storage_status"] == "stored"
    assert payload.metadata["storage_backend"] == "local"
    assert payload.metadata["local_path"] == str(stored.path)
    assert payload.metadata["analysis"]["status"] == "queued"
    assert payload.metadata["analysis"]["engine"] == "ocr"
    assert payload.metadata["analysis"]["relation_type"] == "mentioned_in_evidence"


def test_build_evidence_create_from_s3_upload_marks_bucket_metadata(monkeypatch) -> None:
    monkeypatch.setattr("app.services.evidence.settings.s3_endpoint", "http://minio:9000")
    stored = StoredUpload(
        filename="captura.png",
        content_type="image/png",
        size_bytes=12,
        sha256=SHA256,
        object_key=f"reports/{uuid4()}/evidence/{SHA256}.png",
        storage_backend="s3",
        bucket="verigraph-evidence",
    )

    payload = build_evidence_create_from_stored_upload(stored, description="Captura de chat.")

    assert payload.metadata["storage_status"] == "stored"
    assert payload.metadata["storage_backend"] == "s3"
    assert payload.metadata["s3_bucket"] == "verigraph-evidence"
    assert payload.metadata["s3_endpoint"] == "http://minio:9000"
    assert "local_path" not in payload.metadata


def test_create_report_evidence_writes_audit_log_and_commits() -> None:
    report = build_report()
    session = FakeEvidenceSession([FakeScalarOneResult(report)])
    payload = build_payload()

    response = asyncio.run(
        create_report_evidence(
            session,  # type: ignore[arg-type]
            report.id,
            payload,
        )
    )

    assert session.committed is True
    assert session.refreshed is session.objects[0]
    assert len(session.objects) == 2
    evidence = session.objects[0]
    audit_log = session.objects[1]
    assert isinstance(evidence, EvidenceFile)
    assert response.report_id == str(report.id)
    assert response.filename == "captura.png"
    assert response.size_bytes == 2048
    assert audit_log.action == "report.evidence_added"
    assert audit_log.target_type == "report"
    assert audit_log.target_id == str(report.id)
    assert audit_log.metadata_json["filename"] == "captura.png"
    assert audit_log.metadata_json["sha256"] == SHA256


def test_create_report_evidence_from_upload_stores_file_and_writes_audit_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(storage.settings, "local_evidence_storage_path", str(tmp_path))
    report = build_report()
    session = FakeEvidenceSession([FakeScalarOneResult(report)])
    upload = FakeUploadFile(filename="captura.png", content_type="image/png", content=MINIMAL_PNG)

    response = asyncio.run(
        create_report_evidence_from_upload(
            session,  # type: ignore[arg-type]
            report.id,
            upload,  # type: ignore[arg-type]
            description="Captura de chat.",
        )
    )

    assert upload.closed is True
    assert session.committed is True
    assert len(session.objects) == 2
    evidence = session.objects[0]
    audit_log = session.objects[1]
    assert isinstance(evidence, EvidenceFile)
    assert response.report_id == str(report.id)
    assert response.filename == "captura.png"
    assert response.metadata["storage_status"] == "stored"
    assert response.metadata["analysis"]["engine"] == "ocr"
    assert response.metadata["analysis"]["status"] == "queued"
    assert (tmp_path / evidence.object_key).exists()
    assert audit_log.action == "report.evidence_added"
    assert audit_log.metadata_json["object_key"] == evidence.object_key


def test_list_report_evidence_returns_registered_files() -> None:
    report = build_report()
    payload = build_payload()
    evidence = build_evidence_file(report.id, payload)
    evidence.id = uuid4()
    evidence.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    session = FakeEvidenceSession(
        [
            FakeScalarOneResult(report),
            FakeScalarManyResult([evidence]),
        ]
    )

    response = asyncio.run(
        list_report_evidence(
            session,  # type: ignore[arg-type]
            report.id,
        )
    )

    assert len(response) == 1
    assert response[0].report_id == str(report.id)
    assert response[0].filename == "captura.png"
    assert response[0].sha256 == SHA256


def test_list_report_evidence_raises_when_report_does_not_exist() -> None:
    session = FakeEvidenceSession([FakeScalarOneResult(None)])

    with pytest.raises(ReportNotFoundError):
        asyncio.run(
            list_report_evidence(
                session,  # type: ignore[arg-type]
                uuid4(),
            )
        )

    assert session.committed is False
