"""Create chat session table.

Revision ID: 0004_create_chat_sessions
Revises: 0003_create_chat_logs
Create Date: 2026-05-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_create_chat_sessions"
down_revision: str | None = "0003_create_chat_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "workspace_id",
            sa.Text(),
            server_default=sa.text("'public'"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "chat_sessions_workspace_updated_at_idx",
        "chat_sessions",
        ["workspace_id", "updated_at"],
        unique=False,
    )
    op.add_column(
        "chat_logs",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "chat_logs_session_id_fkey",
        "chat_logs",
        "chat_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "chat_logs_session_created_at_idx",
        "chat_logs",
        ["session_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("chat_logs_session_created_at_idx", table_name="chat_logs")
    op.drop_constraint("chat_logs_session_id_fkey", "chat_logs", type_="foreignkey")
    op.drop_column("chat_logs", "session_id")
    op.drop_index(
        "chat_sessions_workspace_updated_at_idx",
        table_name="chat_sessions",
    )
    op.drop_table("chat_sessions")
