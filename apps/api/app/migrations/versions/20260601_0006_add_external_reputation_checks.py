"""add external reputation checks

Revision ID: 20260601_0006
Revises: 20260527_0005
Create Date: 2026-06-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0006"
down_revision: str | None = "20260527_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_reputation_checks",
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("malicious", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_reputation_checks_entity_id", "external_reputation_checks", ["entity_id"])
    op.create_index("ix_external_reputation_checks_malicious", "external_reputation_checks", ["malicious"])
    op.create_index("ix_external_reputation_checks_severity", "external_reputation_checks", ["severity"])
    op.create_index("ix_external_reputation_checks_source", "external_reputation_checks", ["source"])
    op.create_index("ix_external_reputation_checks_status", "external_reputation_checks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_external_reputation_checks_status", table_name="external_reputation_checks")
    op.drop_index("ix_external_reputation_checks_source", table_name="external_reputation_checks")
    op.drop_index("ix_external_reputation_checks_severity", table_name="external_reputation_checks")
    op.drop_index("ix_external_reputation_checks_malicious", table_name="external_reputation_checks")
    op.drop_index("ix_external_reputation_checks_entity_id", table_name="external_reputation_checks")
    op.drop_table("external_reputation_checks")
