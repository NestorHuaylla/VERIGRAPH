from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import AppealStatus


class AppealCreate(BaseModel):
    appellant_contact: str | None = Field(default=None, max_length=320)
    reason: str = Field(min_length=20, max_length=5000)


class AppealStatusUpdate(BaseModel):
    status: AppealStatus
    reason: str = Field(min_length=5, max_length=2000)


class AppealResponse(BaseModel):
    id: str
    report_id: str
    appellant_contact: str | None
    reason: str
    status: AppealStatus
    resolution_reason: str | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None


class AppealStatusResponse(BaseModel):
    id: str
    report_id: str
    status: AppealStatus
    message: str
