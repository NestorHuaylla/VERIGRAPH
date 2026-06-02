from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import CaseStatus, EntityType, RiskLevel
from app.schemas.graph import GraphMetrics, GraphResponse


class CaseCreate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)


class CaseListItem(BaseModel):
    id: str
    title: str
    summary: str | None
    status: CaseStatus
    risk_level: RiskLevel
    root_entity_id: str | None
    created_at: datetime
    updated_at: datetime | None


class CaseEntityContext(BaseModel):
    id: str
    type: EntityType
    display_value: str
    normalized_value: str


class CaseReportItem(BaseModel):
    id: str
    status: str
    reason: str
    source: str
    created_at: datetime


class CaseDetailResponse(BaseModel):
    id: str
    title: str
    summary: str | None
    status: CaseStatus
    risk_level: RiskLevel
    root_entity: CaseEntityContext | None
    reports: list[CaseReportItem]
    evidence_count: int
    graph: GraphResponse
    graph_metrics: GraphMetrics | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None


class CaseStatusUpdate(BaseModel):
    status: CaseStatus
    reason: str = Field(min_length=5, max_length=2000)


class CaseStatusResponse(BaseModel):
    id: str
    status: CaseStatus
    message: str


class CaseSyncResponse(BaseModel):
    id: str
    snapshot: dict
    message: str
