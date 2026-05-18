from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/ci.yml")


def load_ci_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_ci_workflow_exists() -> None:
    assert WORKFLOW_PATH.exists()


def test_ci_workflow_uses_pgvector_service() -> None:
    workflow = load_ci_workflow()
    postgres = workflow["jobs"]["backend"]["services"]["postgres"]

    assert postgres["image"] == "pgvector/pgvector:pg16"
    assert postgres["env"]["POSTGRES_USER"] == "rag"
    assert postgres["env"]["POSTGRES_DB"] == "rag"


def test_ci_workflow_runs_required_checks() -> None:
    workflow = load_ci_workflow()
    steps = workflow["jobs"]["backend"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)

    assert "uv run ruff check ." in commands
    assert "uv run pytest" in commands
    assert "uv run alembic upgrade head" in commands
    assert "python -m ingestion.ingest" in commands
    assert "python -m backend.app.rag.pipeline_smoke" in commands
    assert "python -m evals.run" in commands
    assert "--fail-on-failure" in commands


def test_ci_workflow_uploads_eval_report() -> None:
    workflow = load_ci_workflow()
    steps = workflow["jobs"]["backend"]["steps"]
    upload_step = next(
        step for step in steps if step.get("name") == "Upload eval report"
    )

    assert upload_step["if"] == "always()"
    assert upload_step["uses"] == "actions/upload-artifact@v4"
    assert upload_step["with"]["path"] == "evals/reports/ci.json"
