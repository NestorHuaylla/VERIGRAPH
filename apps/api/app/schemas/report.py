from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import EntityType, ReviewStatus, RiskLevel
from app.schemas.risk import RiskSignal


class ReportCreate(BaseModel):
    entity_type: EntityType
    entity_value: str = Field(min_length=2, max_length=2000)
    reason: str = Field(min_length=10, max_length=5000)
    reporter_contact: EmailStr | None = None


class ReportResponse(BaseModel):
    id: str
    entity_id: str
    status: str
    risk_score: int
    risk_level: RiskLevel
    message: str


class ReportListItem(BaseModel):
    id: str
    entity_id: str | None
    entity_type: EntityType | None
    entity_value: str | None
    entity_normalized_value: str | None
    status: str
    risk_score: int | None
    risk_level: RiskLevel | None
    created_at: datetime


class ReportDetailResponse(BaseModel):
    id: str
    entity_id: str | None
    entity_type: EntityType | None
    entity_value: str | None
    entity_raw_value: str | None
    entity_normalized_value: str | None
    reporter_contact: str | None
    reason: str
    status: ReviewStatus
    source: str
    risk_score: int | None
    risk_level: RiskLevel | None
    risk_explanation: str | None
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    risk_rules_version: str | None
    metadata: dict
    created_at: datetime
    updated_at: datetime | None


class ReportStatusUpdate(BaseModel):
    status: ReviewStatus
    reason: str = Field(min_length=5, max_length=2000)


class ReportStatusResponse(BaseModel):
    id: str
    status: ReviewStatus
    message: str
