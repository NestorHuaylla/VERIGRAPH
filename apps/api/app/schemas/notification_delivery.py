from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import NotificationDeliveryChannel, NotificationDeliveryStatus


class NotificationDeliveryListItem(BaseModel):
    id: str
    notification_id: str
    channel: NotificationDeliveryChannel
    destination: str | None
    status: NotificationDeliveryStatus
    attempts: int
    last_error: str | None
    sent_at: datetime | None
    next_attempt_at: datetime | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None


class NotificationDeliveryStatusUpdate(BaseModel):
    status: NotificationDeliveryStatus
    error: str | None = Field(default=None, max_length=2000)


class NotificationDeliveryStatusResponse(BaseModel):
    id: str
    status: NotificationDeliveryStatus
    attempts: int
    message: str
