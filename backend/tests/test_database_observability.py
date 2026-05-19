from pathlib import Path

import yaml

LOCAL_COMPOSE_PATH = Path("docker-compose.yml")
PROD_COMPOSE_PATH = Path("docker-compose.prod.yml")
ENV_EXAMPLE_PATH = Path(".env.example")
MIGRATION_PATH = Path(
    "backend/app/db/migrations/versions/0005_enable_pg_stat_statements.py"
)
DOC_PATH = Path("docs/DATABASE_OBSERVABILITY.md")
README_PATH = Path("README.md")
HANDOFF_PATH = Path("docs/PROJECT_HANDOFF.md")
RUNBOOK_PATH = Path("docs/DEPLOYMENT_RUNBOOK.md")


def load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_postgres_compose_enables_slow_query_observability() -> None:
    for compose_path in (LOCAL_COMPOSE_PATH, PROD_COMPOSE_PATH):
        postgres = load_compose(compose_path)["services"]["postgres"]
        command = " ".join(postgres["command"])

        assert "shared_preload_libraries=pg_stat_statements" in command
        assert "pg_stat_statements.track=all" in command
        assert "track_io_timing=on" in command
        assert "log_min_duration_statement=" in command
        assert "POSTGRES_LOG_MIN_DURATION_STATEMENT_MS" in command


def test_pg_stat_statements_migration_exists() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision: str = "0005_enable_pg_stat_statements"' in migration
    assert 'down_revision: str | None = "0004_create_chat_sessions"' in migration
    assert "CREATE EXTENSION IF NOT EXISTS pg_stat_statements" in migration


def test_database_observability_env_var_is_documented() -> None:
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    doc = DOC_PATH.read_text(encoding="utf-8")

    assert "POSTGRES_LOG_MIN_DURATION_STATEMENT_MS=1000" in env_example
    assert "POSTGRES_LOG_MIN_DURATION_STATEMENT_MS" in doc
    assert "pg_stat_statements" in doc
    assert "log_min_duration_statement" in doc


def test_database_observability_doc_is_linked_from_entry_documents() -> None:
    expected_link = "docs/DATABASE_OBSERVABILITY.md"

    assert expected_link in README_PATH.read_text(encoding="utf-8")
    assert expected_link in HANDOFF_PATH.read_text(encoding="utf-8")
    assert expected_link in RUNBOOK_PATH.read_text(encoding="utf-8")
