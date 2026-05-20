import re
from pathlib import Path

MIGRATIONS_DIR = Path("backend/app/db/migrations/versions")
MIGRATION_PATH = Path(
    "backend/app/db/migrations/versions/0007_add_workspace_foreign_keys.py"
)
ARCHIVE_MIGRATION_PATH = Path(
    "backend/app/db/migrations/versions/0008_add_workspace_archive_fields.py"
)
AUDIT_MIGRATION_PATH = Path(
    "backend/app/db/migrations/versions/0009_create_workspace_audit_logs.py"
)
EXPORT_JOB_MIGRATION_PATH = Path(
    "backend/app/db/migrations/versions/0010_create_export_jobs.py"
)


def test_workspace_foreign_key_migration_backfills_existing_workspace_ids() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'down_revision: str | None = "0006_create_workspaces"' in migration
    assert "SELECT DISTINCT workspace_id FROM documents" in migration
    assert "SELECT DISTINCT workspace_id FROM document_chunks" in migration
    assert "SELECT DISTINCT workspace_id FROM chat_sessions" in migration
    assert "SELECT DISTINCT workspace_id FROM chat_logs" in migration
    assert "ON CONFLICT (id) DO NOTHING" in migration


def test_workspace_foreign_key_migration_adds_all_workspace_constraints() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    for constraint_name in (
        "documents_workspace_id_fkey",
        "document_chunks_workspace_id_fkey",
        "chat_sessions_workspace_id_fkey",
        "chat_logs_workspace_id_fkey",
    ):
        assert constraint_name in migration

    assert 'ondelete="RESTRICT"' in migration
    assert 'onupdate="CASCADE"' in migration


def test_workspace_archive_migration_adds_soft_archive_fields() -> None:
    migration = ARCHIVE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision: str = "0008_workspace_archive"' in migration
    assert 'down_revision: str | None = "0007_add_workspace_foreign_keys"' in migration
    assert '"archived_at"' in migration
    assert '"archived_reason"' in migration
    assert "workspaces_archived_at_idx" in migration


def test_workspace_audit_migration_adds_operation_log_table() -> None:
    migration = AUDIT_MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision: str = "0009_workspace_audit_logs"' in migration
    assert 'down_revision: str | None = "0008_workspace_archive"' in migration
    assert '"workspace_audit_logs"' in migration
    assert '"request_id"' in migration
    assert '"actor_hash"' in migration
    assert '"workspace_ids"' in migration
    assert '"workspace_count"' in migration
    assert "workspace_audit_logs_created_at_idx" in migration
    assert "workspace_audit_logs_request_id_idx" in migration
    assert "workspace_audit_logs_workspace_ids_idx" in migration
    assert 'postgresql_using="gin"' in migration


def test_export_job_migration_adds_async_export_table() -> None:
    migration = EXPORT_JOB_MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision: str = "0010_export_jobs"' in migration
    assert 'down_revision: str | None = "0009_workspace_audit_logs"' in migration
    assert '"export_jobs"' in migration
    assert '"workspace_id"' in migration
    assert '"request_id"' in migration
    assert '"actor_hash"' in migration
    assert '"export_type"' in migration
    assert '"format"' in migration
    assert '"status"' in migration
    assert '"filters"' in migration
    assert '"result_uri"' in migration
    assert '"error_message"' in migration
    assert "export_jobs_status_check" in migration
    assert "export_jobs_workspace_created_at_idx" in migration
    assert "export_jobs_status_created_at_idx" in migration
    assert "export_jobs_request_id_idx" in migration
    assert 'ondelete="RESTRICT"' in migration
    assert 'onupdate="CASCADE"' in migration


def test_alembic_revision_ids_fit_current_version_column() -> None:
    for migration_path in MIGRATIONS_DIR.glob("*.py"):
        if migration_path.name == "__init__.py":
            continue

        migration = migration_path.read_text(encoding="utf-8")
        revision_match = re.search(
            r'^revision: str = "([^"]+)"',
            migration,
            re.MULTILINE,
        )

        assert revision_match is not None, f"{migration_path} must define revision"
        assert len(revision_match.group(1)) <= 32
