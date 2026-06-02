"""add appeals

Revision ID: 20260527_0002
Revises: 20260526_0001
Create Date: 2026-05-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260527_0002"
down_revision: str | None = "20260526_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appeals",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appellant_contact", sa.String(length=320), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appeals_report_id", "appeals", ["report_id"])
    op.create_index("ix_appeals_status", "appeals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_appeals_status", table_name="appeals")
    op.drop_index("ix_appeals_report_id", table_name="appeals")
    op.drop_table("appeals")
