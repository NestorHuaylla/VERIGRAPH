from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Appeal(Base, IdMixin, TimestampMixin):
    __tablename__ = "appeals"

    report_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), ForeignKey("reports.id"), index=True)
    appellant_contact: Mapped[str | None] = mapped_column(String(320), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
