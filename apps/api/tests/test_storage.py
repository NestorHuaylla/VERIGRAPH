import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.storage import (
    S3EvidenceStorageError,
    EmptyEvidenceFileError,
    EvidenceFileTooLargeError,
    UnsupportedEvidenceContentTypeError,
    UnsupportedEvidenceStorageBackendError,
    UnsafeEvidenceFilenameError,
    build_local_evidence_object_key,
    read_s3_object_text,
    resolve_object_path,
    sanitize_upload_filename,
    store_evidence_upload,
)


MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


class FakeS3Client:
    def __init__(self, *, head_bucket_error: Exception | None = None) -> None:
        self.head_bucket_error = head_bucket_error
        self.created_buckets: list[str] = []
        self.uploads: list[dict[str, object]] = []
        self.objects: dict[tuple[str, str], bytes] = {}

    def head_bucket(self, *, Bucket: str) -> None:
        if self.head_bucket_error:
            raise self.head_bucket_error

    def create_bucket(self, *, Bucket: str) -> None:
        self.created_buckets.append(Bucket)

    def upload_file(self, Filename: str, Bucket: str, Key: str, ExtraArgs: dict | None = None) -> None:
        content = Path(Filename).read_bytes()
        self.objects[(Bucket, Key)] = content
        self.uploads.append({"Bucket": Bucket, "Key": Key, "ExtraArgs": ExtraArgs or {}})

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        if (Bucket, Key) not in self.objects:
            raise OSError("missing object")
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}


def test_sanitize_upload_filename_rejects_paths() -> None:
    with pytest.raises(UnsafeEvidenceFilenameError):
        sanitize_upload_filename("../captura.png")


def test_resolve_object_path_rejects_escape_from_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_object_path(tmp_path, "../escape.png")


def test_store_evidence_upload_writes_file_and_hashes_content(tmp_path: Path) -> None:
    content = MINIMAL_PNG
    report_id = uuid4()
    upload = FakeUploadFile(filename="captura.png", content_type="image/png", content=content)

    stored = asyncio.run(async_store(upload, report_id=report_id, storage_root=tmp_path))

    assert stored.filename == "captura.png"
    assert stored.content_type == "image/png"
    assert stored.size_bytes == len(content)
    assert stored.sha256 == hashlib.sha256(content).hexdigest()
    assert stored.object_key == build_local_evidence_object_key(report_id, "captura.png", stored.sha256)
    assert stored.storage_backend == "local"
    assert stored.path.exists()
    assert stored.path.read_bytes() == content
    assert upload.closed is True


def test_store_evidence_upload_writes_s3_object_and_hashes_content(tmp_path: Path, monkeypatch) -> None:
    content = MINIMAL_PNG
    report_id = uuid4()
    upload = FakeUploadFile(filename="captura.png", content_type="image/png", content=content)
    s3_client = FakeS3Client()
    monkeypatch.setattr("app.services.storage.settings.s3_bucket_evidence", "evidence-bucket")

    stored = asyncio.run(
        async_store(
            upload,
            report_id=report_id,
            storage_root=tmp_path,
            storage_backend="s3",
            s3_client=s3_client,
        )
    )

    assert stored.filename == "captura.png"
    assert stored.content_type == "image/png"
    assert stored.size_bytes == len(content)
    assert stored.sha256 == hashlib.sha256(content).hexdigest()
    assert stored.storage_backend == "s3"
    assert stored.path is None
    assert stored.bucket == "evidence-bucket"
    assert s3_client.uploads[0]["Bucket"] == "evidence-bucket"
    assert s3_client.uploads[0]["Key"] == stored.object_key
    extra_args = s3_client.uploads[0]["ExtraArgs"]
    assert extra_args["ContentType"] == "image/png"
    assert extra_args["Metadata"]["sha256"] == stored.sha256
    assert s3_client.objects[("evidence-bucket", stored.object_key)] == content
    assert list((tmp_path / "_tmp").glob("*.part")) == []
    assert upload.closed is True


def test_store_evidence_upload_rejects_unsupported_content_type(tmp_path: Path) -> None:
    upload = FakeUploadFile(filename="malware.exe", content_type="application/x-msdownload", content=b"x")

    with pytest.raises(UnsupportedEvidenceContentTypeError):
        asyncio.run(async_store(upload, report_id=uuid4(), storage_root=tmp_path))


def test_store_evidence_upload_rejects_empty_file(tmp_path: Path) -> None:
    upload = FakeUploadFile(filename="captura.png", content_type="image/png", content=b"")

    with pytest.raises(EmptyEvidenceFileError):
        asyncio.run(async_store(upload, report_id=uuid4(), storage_root=tmp_path))


def test_store_evidence_upload_rejects_oversized_file(tmp_path: Path) -> None:
    upload = FakeUploadFile(filename="captura.txt", content_type="text/plain", content=b"12345")

    with pytest.raises(EvidenceFileTooLargeError):
        asyncio.run(async_store(upload, report_id=uuid4(), storage_root=tmp_path, max_size_bytes=4))


def test_store_evidence_upload_rejects_unknown_backend(tmp_path: Path) -> None:
    upload = FakeUploadFile(filename="captura.txt", content_type="text/plain", content=b"x")

    with pytest.raises(UnsupportedEvidenceStorageBackendError):
        asyncio.run(async_store(upload, report_id=uuid4(), storage_root=tmp_path, storage_backend="ftp"))


def test_read_s3_object_text_decodes_utf8(monkeypatch) -> None:
    s3_client = FakeS3Client()
    s3_client.objects[("evidence-bucket", "reports/1/evidence/test.txt")] = "Linea uno".encode()
    monkeypatch.setattr("app.services.storage.settings.s3_bucket_evidence", "evidence-bucket")

    text = read_s3_object_text("reports/1/evidence/test.txt", s3_client=s3_client)

    assert text == "Linea uno"


def test_read_s3_object_text_wraps_storage_error(monkeypatch) -> None:
    monkeypatch.setattr("app.services.storage.settings.s3_bucket_evidence", "evidence-bucket")

    with pytest.raises(S3EvidenceStorageError):
        read_s3_object_text("missing.txt", s3_client=FakeS3Client())


async def async_store(
    upload: FakeUploadFile,
    *,
    report_id,
    storage_root: Path,
    max_size_bytes: int = 1024,
    storage_backend: str = "local",
    s3_client=None,
):
    return await store_evidence_upload(
        upload,  # type: ignore[arg-type]
        report_id=report_id,
        storage_root=storage_root,
        max_size_bytes=max_size_bytes,
        storage_backend=storage_backend,
        s3_client=s3_client,
    )
