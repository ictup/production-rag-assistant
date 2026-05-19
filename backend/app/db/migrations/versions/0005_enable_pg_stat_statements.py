"""Enable pg_stat_statements extension.

Revision ID: 0005_enable_pg_stat_statements
Revises: 0004_create_chat_sessions
Create Date: 2026-05-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_enable_pg_stat_statements"
down_revision: str | None = "0004_create_chat_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
