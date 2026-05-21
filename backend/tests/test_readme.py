from pathlib import Path

README_PATH = Path("README.md")


def test_readme_has_project_homepage_sections() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    required_sections = [
        "# Production RAG Assistant",
        "## Why This Project Matters",
        "## Project Highlights",
        "## Release Status",
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
        "uv run python -m evals.agent_run --format summary "
        "--fail-on-failure --no-output",
        "uv run python -m backend.app.rag.pipeline_smoke",
        "uv run python -m evals.document_management_smoke",
        "http://127.0.0.1:8000/app/",
        "docs/releases/v0.1.0.md",
        "docs/releases/v0.1.0-github-release.md",
        "docs/PORTFOLIO_PRESENTATION.md",
        "docs/agentic_rag_extension.md",
        "POST /agent/support-triage",
        "GET /agent/approvals",
        "POST /agent/approvals/{approval_id}/decision",
        "rag_search_tool",
        "ticket_lookup_tool",
        "draft_response_tool",
        "agent_approvals",
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


def test_readme_has_public_portfolio_positioning() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    required_snippets = [
        "[![CI](https://github.com/ictup/production-rag-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/ictup/production-rag-assistant/actions/workflows/ci.yml)",
        "[![Tag](https://img.shields.io/github/v/tag/ictup/production-rag-assistant?label=tag)](https://github.com/ictup/production-rag-assistant/releases/tag/v0.1.0)",
        "[![Python](https://img.shields.io/badge/python-3.11-blue)](pyproject.toml)",
        "[![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688)](backend/app/main.py)",
        "[![Postgres](https://img.shields.io/badge/Postgres-pgvector-336791)](docker-compose.prod.yml)",
        "[![Tests](https://img.shields.io/badge/test%20suite-600%2B%20tests-brightgreen)](backend/tests)",
        "portfolio-grade AI backend project",
        "This is not a notebook demo.",
        "| Area | What is implemented |",
        "`v0.1.0` is the production readiness baseline",
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
