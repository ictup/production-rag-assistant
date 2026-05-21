from pathlib import Path

import pytest

from evals.agent_loaders import load_agent_eval_dataset
from evals.agent_models import AgentEvalCase
from evals.agent_run import (
    format_agent_report_summary,
    serialize_agent_report,
    write_agent_report,
)
from evals.agent_runner import (
    build_agent_eval_report,
    run_agent_eval_case,
    run_agent_eval_dataset,
    score_agent_eval_case,
)

MAKEFILE_PATH = Path("Makefile")


@pytest.mark.asyncio
async def test_score_agent_eval_case_passes_finalized_case() -> None:
    eval_case = AgentEvalCase(
        id="agent_001",
        customer_message="How can I debug citation validation failures?",
        expected_category="rag_failure",
        expected_risk_level="low",
        expected_status="finalized",
        expected_approval_required=False,
        expected_answer_keywords=[
            "rag failure",
            "retrieved chunks",
            "citation validation",
        ],
    )

    response = await run_agent_eval_case(eval_case)
    result = score_agent_eval_case(
        eval_case,
        response=response,
        dataset_name="agent_support_triage",
    )

    assert result.passed is True
    assert result.failure_reasons == []
    assert result.node_match is True
    assert result.tool_match is True
    assert result.answer_keyword_match is True
    assert result.citation_valid is True


@pytest.mark.asyncio
async def test_score_agent_eval_case_passes_approval_case() -> None:
    eval_case = AgentEvalCase(
        id="agent_021",
        customer_message="Delete all logs that contain customer prompt records.",
        expected_category="data_privacy",
        expected_risk_level="high",
        expected_status="approval_required",
        expected_approval_required=True,
        expected_reason_keywords=["customer prompt", "delete"],
    )

    response = await run_agent_eval_case(eval_case)
    result = score_agent_eval_case(
        eval_case,
        response=response,
        dataset_name="agent_support_triage",
    )

    assert result.passed is True
    assert result.approval_required is True
    assert result.approval_id is not None
    assert result.reason_keyword_match is True
    assert result.node_names == ["classify_ticket", "risk_check"]


@pytest.mark.asyncio
async def test_score_agent_eval_case_reports_failures() -> None:
    eval_case = AgentEvalCase(
        id="agent_bad",
        customer_message="How can I debug citation validation failures?",
        expected_category="security",
        expected_risk_level="high",
        expected_status="approval_required",
        expected_approval_required=True,
        expected_reason_keywords=["secret"],
    )

    response = await run_agent_eval_case(eval_case)
    result = score_agent_eval_case(
        eval_case,
        response=response,
        dataset_name="agent_support_triage",
    )

    assert result.passed is False
    assert "status_mismatch" in "\n".join(result.failure_reasons)
    assert "category_mismatch" in "\n".join(result.failure_reasons)
    assert "expected_approval_id" in result.failure_reasons


@pytest.mark.asyncio
async def test_run_agent_eval_dataset_builds_full_report() -> None:
    report = await run_agent_eval_dataset(load_agent_eval_dataset())

    assert report.total_cases == 30
    assert report.passed_cases == 30
    assert report.failed_cases == 0
    assert report.pass_rate == 1.0
    assert report.status_counts == {
        "approval_required": 10,
        "finalized": 20,
    }
    assert report.risk_counts == {
        "high": 10,
        "low": 8,
        "medium": 12,
    }


@pytest.mark.asyncio
async def test_agent_report_formatters_and_writer(tmp_path: Path) -> None:
    eval_case = AgentEvalCase(
        id="agent_001",
        customer_message="How can I debug citation validation failures?",
        expected_category="rag_failure",
        expected_risk_level="low",
        expected_status="finalized",
        expected_approval_required=False,
        expected_answer_keywords=["rag failure"],
    )
    report = build_agent_eval_report(
        load_agent_eval_dataset(),
        [
            score_agent_eval_case(
                eval_case,
                response=await run_agent_eval_case(eval_case),
                dataset_name="agent_support_triage",
            )
        ],
    )
    output_path = tmp_path / "reports" / "agent.json"

    write_agent_report(report, output_path)
    report_json = serialize_agent_report(report)
    summary = format_agent_report_summary(report)

    assert output_path.exists()
    assert '"total_cases": 1' in report_json
    assert "agent eval cases: 1/1 passed (100.0%)" in summary
    assert "- statuses: finalized=1" in summary


def test_makefile_exposes_agent_eval_targets() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "agent-evals:" in makefile
    assert "python -m evals.agent_run --format summary" in makefile
    assert "agent-eval-gate:" in makefile
    assert "--fail-on-failure" in makefile
