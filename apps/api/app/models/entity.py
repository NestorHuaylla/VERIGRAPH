from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Entity(Base, IdMixin, TimestampMixin):
    __tablename__ = "entities"

    type: Mapped[str] = mapped_column(String(60), index=True)
    raw_value: Mapped[str] = mapped_column(Text)
    normalized_value: Mapped[str] = mapped_column(Text, index=True)
    display_value: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("type", "normalized_value", name="uq_entities_type_normalized"),
    )


class EntityRelation(Base, IdMixin, TimestampMixin):
    __tablename__ = "entity_relations"

    source_entity_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), ForeignKey("entities.id"), index=True)
    target_entity_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), ForeignKey("entities.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(80), index=True)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", "relation_type", name="uq_entity_relations_source_target_type"),
    )
