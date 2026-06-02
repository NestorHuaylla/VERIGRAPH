from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    id: str
    actor_user_id: str | None
    action: str
    target_type: str
    target_id: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
