from pydantic import BaseModel

from app.core.constants import EntityType
from app.core.constants import RiskLevel


class RiskSignal(BaseModel):
    code: str
    label: str
    weight: int


class RiskScoreResponse(BaseModel):
    score: int
    level: RiskLevel
    explanation: str
    signals: list[RiskSignal]


class PublicRiskResponse(BaseModel):
    entity_type: EntityType
    normalized_value: str
    entity_id: str | None
    related_reports: int
    score: int
    level: RiskLevel
    explanation: str
    signals: list[RiskSignal]
    data_source: str
