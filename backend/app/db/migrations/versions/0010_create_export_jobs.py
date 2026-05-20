"""Create export jobs table.

Revision ID: 0010_export_jobs
Revises: 0009_workspace_audit_logs
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_export_jobs"
down_revision: str | None = "0009_workspace_audit_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("actor_hash", sa.String(length=64), nullable=False),
        sa.Column("export_type", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("result_uri", sa.Text(), nullable=True),
        sa.Column("result_media_type", sa.Text(), nullable=True),
        sa.Column("result_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="export_jobs_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "export_jobs_workspace_created_at_idx",
        "export_jobs",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "export_jobs_status_created_at_idx",
        "export_jobs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "export_jobs_request_id_idx",
        "export_jobs",
        ["request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("export_jobs_request_id_idx", table_name="export_jobs")
    op.drop_index("export_jobs_status_created_at_idx", table_name="export_jobs")
    op.drop_index("export_jobs_workspace_created_at_idx", table_name="export_jobs")
    op.drop_table("export_jobs")
