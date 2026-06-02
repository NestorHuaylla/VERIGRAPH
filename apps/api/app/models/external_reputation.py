from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class ExternalReputationCheck(Base, IdMixin, TimestampMixin):
    __tablename__ = "external_reputation_checks"

    entity_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), ForeignKey("entities.id"), index=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(40), index=True)
    malicious: Mapped[bool] = mapped_column(default=False, index=True)
    summary: Mapped[str] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
