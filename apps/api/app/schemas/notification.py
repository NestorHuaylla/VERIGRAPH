from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import NotificationSeverity


class NotificationListItem(BaseModel):
    id: str
    user_id: str | None
    event_type: str
    title: str
    message: str
    severity: NotificationSeverity
    is_read: bool
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None


class NotificationReadResponse(BaseModel):
    id: str
    is_read: bool
    message: str
