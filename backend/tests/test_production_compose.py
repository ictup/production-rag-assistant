from pathlib import Path

import yaml

COMPOSE_PATH = Path("docker-compose.prod.yml")
MAKEFILE_PATH = Path("Makefile")


def load_production_compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_production_compose_defines_api_migrate_and_postgres() -> None:
    compose = load_production_compose()
    services = compose["services"]

    assert COMPOSE_PATH.exists()
    assert set(services) == {"api", "migrate", "postgres"}
    assert services["postgres"]["image"] == "pgvector/pgvector:pg16"
    assert services["api"]["image"] == "production-rag-assistant:${APP_VERSION:-local}"
    assert services["api"]["build"]["dockerfile"] == "Dockerfile"


def test_production_compose_uses_internal_database_urls() -> None:
    compose = load_production_compose()

    for service_name in ("api", "migrate"):
        environment = compose["services"][service_name]["environment"]
        assert "@postgres:5432" in environment["DATABASE_URL"]
        assert "@postgres:5432" in environment["SYNC_DATABASE_URL"]
        assert "localhost" not in environment["DATABASE_URL"]
        assert environment["ENV"] == "production"


def test_production_compose_orders_healthcheck_migration_and_api() -> None:
    compose = load_production_compose()
    services = compose["services"]

    assert services["postgres"]["healthcheck"]["test"][0] == "CMD-SHELL"
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["migrate"]["depends_on"]["postgres"]["condition"] == (
        "service_healthy"
    )
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["api"]["healthcheck"]["test"][0] == "CMD"


def test_production_makefile_targets_exist() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "prod-config:" in content
    assert "docker compose -f docker-compose.prod.yml config --quiet" in content
    assert "prod-build:" in content
    assert "prod-up:" in content
    assert "prod-down:" in content
    assert "prod-logs:" in content
