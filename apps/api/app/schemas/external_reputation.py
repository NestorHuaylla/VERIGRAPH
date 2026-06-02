from uuid import UUID

from pydantic import BaseModel, Field


class ExternalReputationSourceResult(BaseModel):
    source: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=80)
    malicious: bool = False
    severity: str = Field(default="none", min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=2000)
    reference: str | None = None
    raw: dict = Field(default_factory=dict)


class ExternalReputationCheckCreate(BaseModel):
    source: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=80)
    malicious: bool = False
    severity: str = Field(default="none", min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=2000)
    reference: str | None = None
    raw: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ExternalReputationBatchCreate(BaseModel):
    checks: list[ExternalReputationCheckCreate] = Field(min_length=1, max_length=20)
    metadata: dict = Field(default_factory=dict)


class ExternalReputationCheckResponse(BaseModel):
    id: UUID
    entity_id: UUID
    source: str
    status: str
    malicious: bool
    severity: str
    summary: str
    reference: str | None
    raw: dict
    metadata: dict
    created_at: str


class ExternalReputationSummary(BaseModel):
    malicious: bool
    malicious_sources: list[str]
    checked_sources: list[str]
    highest_severity: str


class ExternalReputationBatchResponse(BaseModel):
    checks: list[ExternalReputationCheckResponse]
    summary: ExternalReputationSummary
