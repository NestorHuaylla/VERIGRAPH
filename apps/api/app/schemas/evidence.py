from datetime import datetime

from pydantic import BaseModel, Field, field_validator


MAX_EVIDENCE_FILE_SIZE_BYTES = 20 * 1024 * 1024
ALLOWED_EVIDENCE_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/plain",
    }
)


class EvidenceCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    size_bytes: int = Field(ge=1, le=MAX_EVIDENCE_FILE_SIZE_BYTES)
    sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    object_key: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=1000)
    metadata: dict = Field(default_factory=dict)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        filename = value.strip()
        if not filename or "/" in filename or "\\" in filename:
            raise ValueError("Evidence filename must not include a path.")
        return filename

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        content_type = value.strip().lower()
        if content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES:
            raise ValueError("Evidence content type is not allowed.")
        return content_type

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()

    @field_validator("object_key")
    @classmethod
    def validate_object_key(cls, value: str | None) -> str | None:
        if value is None:
            return None

        object_key = value.strip().replace("\\", "/")
        parts = object_key.split("/")
        if not object_key or object_key.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Evidence object key must be a relative storage path.")
        return object_key


class EvidenceResponse(BaseModel):
    id: str
    report_id: str
    object_key: str
    filename: str
    content_type: str
    size_bytes: int | None
    sha256: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
