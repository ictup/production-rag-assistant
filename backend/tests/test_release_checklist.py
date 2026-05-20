from pathlib import Path

RELEASE_CHECKLIST_PATH = Path("docs/RELEASE_CHECKLIST.md")
README_PATH = Path("README.md")
RUNBOOK_PATH = Path("docs/DEPLOYMENT_RUNBOOK.md")
HANDOFF_PATH = Path("docs/PROJECT_HANDOFF.md")


def test_release_checklist_exists_and_covers_release_gates() -> None:
    checklist = RELEASE_CHECKLIST_PATH.read_text(encoding="utf-8")

    required_sections = [
        "## Release Scope",
        "## Local Verification",
        "## Production Configuration Gate",
        "## Secret Scan",
        "## CI Gate",
        "## Deployment Dry Run",
        "## Release Tag",
        "## Release Notes",
        "## Rollback Readiness",
    ]
    missing_sections = [
        section for section in required_sections if section not in checklist
    ]

    assert missing_sections == []


def test_release_checklist_documents_required_commands() -> None:
    checklist = RELEASE_CHECKLIST_PATH.read_text(encoding="utf-8")

    required_commands = [
        "uv run ruff check .",
        "uv run pytest",
        "uv run python -m backend.app.core.config_check",
        "uv run python -m backend.app.core.config_check --production",
        "docker compose -f docker-compose.prod.yml config --quiet",
        "uv run python -m backend.app.rag.pipeline_smoke",
        "uv run python -m evals.document_management_smoke",
        'rg -n "s[k]-"',
        "git tag -a v0.1.0",
        "git push origin v0.1.0",
    ]
    missing_commands = [
        command for command in required_commands if command not in checklist
    ]

    assert missing_commands == []


def test_release_checklist_is_linked_from_entry_docs() -> None:
    expected_link = "docs/RELEASE_CHECKLIST.md"

    assert expected_link in README_PATH.read_text(encoding="utf-8")
    assert expected_link in RUNBOOK_PATH.read_text(encoding="utf-8")
    assert expected_link in HANDOFF_PATH.read_text(encoding="utf-8")
