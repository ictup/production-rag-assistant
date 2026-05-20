from pathlib import Path

RUNBOOK_PATH = Path("docs/DEPLOYMENT_RUNBOOK.md")
README_PATH = Path("README.md")
HANDOFF_PATH = Path("docs/PROJECT_HANDOFF.md")
CONFIGURATION_PATH = Path("docs/CONFIGURATION.md")


def test_deployment_runbook_exists_and_covers_core_operations() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    required_sections = [
        "## Prerequisites",
        "## Initial Setup",
        "## First Deployment",
        "## Verification",
        "## Logs and Inspection",
        "## Update Procedure",
        "## Stop and Restart",
        "## Backup and Recovery",
        "## Common Failures",
    ]

    missing_sections = [
        section
        for section in required_sections
        if section not in runbook
    ]

    assert missing_sections == []


def test_deployment_runbook_uses_quiet_compose_config() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "docker compose -f docker-compose.prod.yml config --quiet" in runbook
    assert "docker compose config" not in runbook


def test_deployment_runbook_documents_health_logs_and_shutdown() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "curl.exe http://127.0.0.1:8000/health" in runbook
    assert "docker compose -f docker-compose.prod.yml logs -f api" in runbook
    assert "docker compose -f docker-compose.prod.yml down" in runbook
    assert "python -m backend.app.core.config_check --production" in runbook


def test_deployment_runbook_is_linked_from_entry_documents() -> None:
    expected_link = "docs/DEPLOYMENT_RUNBOOK.md"

    assert expected_link in README_PATH.read_text(encoding="utf-8")
    assert expected_link in HANDOFF_PATH.read_text(encoding="utf-8")
    assert expected_link in CONFIGURATION_PATH.read_text(encoding="utf-8")


def test_deployment_runbook_links_release_checklist() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "docs/RELEASE_CHECKLIST.md" in runbook
    assert "uv run python -m backend.app.core.config_check --production" in runbook


def test_deployment_runbook_points_to_secret_manager_mapping() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "docs/SECRET_MANAGER_MAPPING.md" in runbook
    assert "deployment platform's" in runbook
    assert "secret store" in runbook
    assert "API_KEYS" in runbook
    assert "OPENAI_API_KEY" in runbook
