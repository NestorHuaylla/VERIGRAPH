from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Report(Base, IdMixin, TimestampMixin):
    __tablename__ = "reports"

    entity_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    reporter_contact: Mapped[str | None] = mapped_column(String(320), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    source: Mapped[str] = mapped_column(String(60), default="public_form")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

