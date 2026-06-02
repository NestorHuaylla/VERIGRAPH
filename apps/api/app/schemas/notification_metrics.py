from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import NotificationDeliveryChannel


class NotificationDeliveryChannelMetrics(BaseModel):
    channel: NotificationDeliveryChannel
    total: int
    pending: int
    scheduled: int
    sent: int
    failed: int


class LastFailedNotificationDelivery(BaseModel):
    id: str
    notification_id: str
    channel: NotificationDeliveryChannel
    destination: str | None
    attempts: int
    last_error: str | None
    status: str
    next_attempt_at: datetime | None
    created_at: datetime


class NotificationMetricsResponse(BaseModel):
    notifications_total: int
    notifications_unread: int
    notifications_by_severity: dict[str, int] = Field(default_factory=dict)
    deliveries_total: int
    deliveries_pending: int
    deliveries_scheduled: int
    deliveries_due: int
    deliveries_sent: int
    deliveries_failed: int
    deliveries_by_channel: list[NotificationDeliveryChannelMetrics] = Field(default_factory=list)
    last_failed_delivery: LastFailedNotificationDelivery | None = None
