from __future__ import annotations

import hashlib
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from fastapi import UploadFile

from app.core.config import settings
from app.schemas.evidence import ALLOWED_EVIDENCE_CONTENT_TYPES, MAX_EVIDENCE_FILE_SIZE_BYTES
from app.services.exif import ExifStripError, ExifStripResult, strip_exif_from_file


CHUNK_SIZE_BYTES = 1024 * 1024


class EvidenceStorageError(Exception):
    pass


class EmptyEvidenceFileError(EvidenceStorageError):
    def __init__(self) -> None:
        super().__init__("Evidence file is empty.")


class EvidenceFileTooLargeError(EvidenceStorageError):
    def __init__(self) -> None:
        super().__init__("Evidence file exceeds the maximum allowed size.")


class UnsupportedEvidenceContentTypeError(EvidenceStorageError):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"Evidence content type is not allowed: {content_type}.")
        self.content_type = content_type


class UnsafeEvidenceFilenameError(EvidenceStorageError):
    def __init__(self) -> None:
        super().__init__("Evidence filename must not include a path.")


class UnsupportedEvidenceStorageBackendError(EvidenceStorageError):
    def __init__(self, backend: str) -> None:
        super().__init__(f"Unsupported evidence storage backend: {backend}.")
        self.backend = backend


class S3EvidenceStorageError(EvidenceStorageError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class S3Client(Protocol):
    def head_bucket(self, *, Bucket: str) -> Any:
        pass

    def create_bucket(self, *, Bucket: str) -> Any:
        pass

    def upload_file(self, Filename: str, Bucket: str, Key: str, ExtraArgs: dict[str, Any] | None = None) -> Any:
        pass

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        pass


@dataclass(frozen=True)
class StoredUpload:
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    object_key: str
    storage_backend: str
    path: Path | None = None
    bucket: str | None = None
    exif: ExifStripResult | None = None


async def store_evidence_upload(
    upload_file: UploadFile,
    *,
    report_id: UUID,
    storage_root: Path | None = None,
    max_size_bytes: int = MAX_EVIDENCE_FILE_SIZE_BYTES,
    storage_backend: str | None = None,
    s3_client: S3Client | None = None,
) -> StoredUpload:
    filename = sanitize_upload_filename(upload_file.filename)
    content_type = normalize_content_type(upload_file.content_type)
    backend = normalize_storage_backend(storage_backend or settings.evidence_storage_backend)
    root = resolve_storage_root(storage_root)
    temp_path = build_temp_path(root)

    hasher = hashlib.sha256()
    size_bytes = 0
    try:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with temp_path.open("wb") as output:
            while chunk := await upload_file.read(CHUNK_SIZE_BYTES):
                size_bytes += len(chunk)
                if size_bytes > max_size_bytes:
                    raise EvidenceFileTooLargeError()
                hasher.update(chunk)
                output.write(chunk)

        if size_bytes == 0:
            raise EmptyEvidenceFileError()

        original_sha256 = hasher.hexdigest()
        try:
            exif_result = strip_exif_from_file(temp_path, content_type=content_type)
        except ExifStripError as exc:
            raise EvidenceStorageError(f"Could not strip evidence image metadata: {exc}") from exc
        size_bytes = exif_result.stripped_size_bytes
        sha256 = hash_file_sha256(temp_path)
        object_key = build_evidence_object_key(report_id, filename, sha256)
        if backend == "s3":
            await store_temp_file_in_s3(
                temp_path,
                object_key=object_key,
                content_type=content_type,
                sha256=sha256,
                size_bytes=size_bytes,
                original_sha256=original_sha256,
                s3_client=s3_client,
            )
            return StoredUpload(
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=sha256,
                object_key=object_key,
                storage_backend="s3",
                bucket=settings.s3_bucket_evidence,
                exif=exif_result,
            )

        final_path = resolve_object_path(root, object_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(final_path)
        return StoredUpload(
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            object_key=object_key,
            storage_backend="local",
            path=final_path,
            exif=exif_result,
        )
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        await upload_file.close()


def sanitize_upload_filename(filename: str | None) -> str:
    if not filename:
        raise UnsafeEvidenceFilenameError()

    clean_name = filename.strip()
    if not clean_name or "/" in clean_name or "\\" in clean_name:
        raise UnsafeEvidenceFilenameError()
    return clean_name


def normalize_content_type(content_type: str | None) -> str:
    normalized_content_type = (content_type or "").strip().lower()
    if normalized_content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES:
        raise UnsupportedEvidenceContentTypeError(normalized_content_type or "unknown")
    return normalized_content_type


def resolve_storage_root(storage_root: Path | None = None) -> Path:
    root = storage_root or Path(settings.local_evidence_storage_path)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def build_temp_path(storage_root: Path) -> Path:
    return storage_root / "_tmp" / f"{uuid4()}.part"


def hash_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE_BYTES), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_storage_backend(storage_backend: str) -> str:
    backend = storage_backend.strip().lower()
    if backend not in {"local", "s3"}:
        raise UnsupportedEvidenceStorageBackendError(backend)
    return backend


def build_evidence_object_key(report_id: UUID, filename: str, sha256: str) -> str:
    extension = Path(filename).suffix.lower()
    return f"reports/{report_id}/evidence/{sha256}{extension}"


def build_local_evidence_object_key(report_id: UUID, filename: str, sha256: str) -> str:
    return build_evidence_object_key(report_id, filename, sha256)


def resolve_object_path(storage_root: Path, object_key: str) -> Path:
    root = storage_root.resolve()
    path = (root / object_key).resolve()
    path.relative_to(root)
    return path


async def store_temp_file_in_s3(
    temp_path: Path,
    *,
    object_key: str,
    content_type: str,
    sha256: str,
    size_bytes: int,
    original_sha256: str | None = None,
    s3_client: S3Client | None = None,
) -> None:
    client = s3_client or build_s3_client()
    bucket = settings.s3_bucket_evidence
    try:
        await asyncio.to_thread(ensure_s3_bucket, client, bucket)
        await asyncio.to_thread(
            client.upload_file,
            str(temp_path),
            bucket,
            object_key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {
                    "sha256": sha256,
                    "original_sha256": original_sha256 or sha256,
                    "size_bytes": str(size_bytes),
                    "source": "verigraph-evidence",
                },
            },
        )
    except (BotoCoreError, ClientError, OSError) as exc:
        raise S3EvidenceStorageError(f"Could not store evidence in S3: {exc}") from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()


def build_s3_client() -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def ensure_s3_bucket(client: S3Client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        status_code = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
        if status_code not in {404, 403}:
            raise
        client.create_bucket(Bucket=bucket)


def read_s3_object_text(object_key: str, *, s3_client: S3Client | None = None) -> str:
    client = s3_client or build_s3_client()
    try:
        response = client.get_object(Bucket=settings.s3_bucket_evidence, Key=object_key)
        body = response["Body"].read()
    except (BotoCoreError, ClientError, OSError, KeyError) as exc:
        raise S3EvidenceStorageError(f"Could not read evidence from S3: {exc}") from exc
    return body.decode("utf-8", errors="replace")
