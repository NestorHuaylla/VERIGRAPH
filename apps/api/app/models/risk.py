from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class RiskRule(Base, IdMixin, TimestampMixin):
    __tablename__ = "risk_rules"

    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True)


class RiskScore(Base, IdMixin, TimestampMixin):
    __tablename__ = "risk_scores"

    entity_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), ForeignKey("entities.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(40), index=True)
    explanation: Mapped[str] = mapped_column(Text)
    signals: Mapped[dict] = mapped_column(JSONB, default=dict)
    rules_version: Mapped[str] = mapped_column(String(40), default="v1")

