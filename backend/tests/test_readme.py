from pathlib import Path

README_PATH = Path("README.md")


def test_readme_has_project_homepage_sections() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    required_sections = [
        "# Production RAG Assistant",
        "## What Is Included",
        "## Architecture",
        "## Repository Map",
        "## Quick Start With Docker",
        "## Local Development",
        "## Configuration Model",
        "## Common API Calls",
        "## Validation Checklist",
        "## Documentation",
    ]

    missing_sections = [
        section
        for section in required_sections
        if section not in readme
    ]

    assert missing_sections == []


def test_readme_documents_core_commands_and_links() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    required_snippets = [
        "docker compose -f docker-compose.prod.yml config --quiet",
        "uv run python -m backend.app.core.config_check --production",
        "docker compose -f docker-compose.prod.yml up -d --build",
        "uv run ruff check .",
        "uv run pytest",
        "uv run python -m backend.app.core.config_check",
        "uv run python -m evals.run --format summary --fail-on-failure --no-output",
        "uv run python -m backend.app.rag.pipeline_smoke",
        "uv run python -m evals.document_management_smoke",
        "http://127.0.0.1:8000/app/",
        "docs/PROJECT_HANDOFF.md",
        "docs/CONFIGURATION.md",
        "docs/SECRET_MANAGER_MAPPING.md",
        "docs/DEPLOYMENT_RUNBOOK.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/OBSERVABILITY.md",
        "docs/DATABASE_OBSERVABILITY.md",
        "docs/EVAL_TRENDS.md",
    ]

    missing_snippets = [
        snippet
        for snippet in required_snippets
        if snippet not in readme
    ]

    assert missing_snippets == []


def test_readme_keeps_default_mode_secret_safe() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "Fake providers are enabled out of the box" in readme
    assert "OPENAI_API_KEY=<set in local .env or secret manager>" in readme
    assert "s[k]-" in readme
    assert "never real keys" in readme.lower()
