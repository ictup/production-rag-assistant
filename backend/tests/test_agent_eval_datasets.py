import json
from pathlib import Path

import pytest

from evals.agent_loaders import (
    DEFAULT_AGENT_EVAL_DATASET,
    load_agent_eval_dataset,
    parse_agent_eval_case,
)
from evals.agent_models import (
    APPROVAL_AGENT_NODES,
    FINALIZED_AGENT_NODES,
    AgentEvalCase,
)
from evals.loaders import EvalDatasetError


def test_parse_agent_eval_case_normalizes_defaults() -> None:
    eval_case = parse_agent_eval_case(
        {
            "id": " agent_001 ",
            "customer_message": " How can I debug citation validation? ",
            "expected_category": "rag_failure",
            "expected_risk_level": "low",
            "expected_status": "finalized",
            "expected_approval_required": False,
            "expected_answer_keywords": [" citation ", ""],
        }
    )

    assert eval_case == AgentEvalCase(
        id="agent_001",
        customer_message="How can I debug citation validation?",
        expected_category="rag_failure",
        expected_risk_level="low",
        expected_status="finalized",
        expected_approval_required=False,
        expected_answer_keywords=["citation"],
        expected_nodes=FINALIZED_AGENT_NODES,
    )
    assert eval_case.ticket_id is None
    assert eval_case.expected_citation_valid is True


def test_parse_agent_eval_case_rejects_invalid_contract() -> None:
    with pytest.raises(EvalDatasetError, match="expected_reason_keywords"):
        parse_agent_eval_case(
            {
                "id": "agent_001",
                "customer_message": "Delete all logs with customer prompts.",
                "expected_category": "data_privacy",
                "expected_risk_level": "high",
                "expected_status": "approval_required",
                "expected_approval_required": True,
            }
        )


def test_load_agent_eval_dataset_loads_30_support_cases() -> None:
    dataset = load_agent_eval_dataset()

    assert dataset.name == "agent_support_triage"
    assert dataset.path == DEFAULT_AGENT_EVAL_DATASET
    assert dataset.total_cases == 30
    assert dataset.cases[0].id == "agent_001"
    assert dataset.cases[-1].id == "agent_030"
    assert {
        eval_case.expected_category
        for eval_case in dataset.cases
    } == {
        "data_privacy",
        "deployment",
        "evaluation",
        "rag_failure",
        "rate_limit",
        "security",
        "serving_latency",
        "unknown",
    }
    assert sum(
        1 for eval_case in dataset.cases if eval_case.expected_approval_required
    ) == 10
    assert all(
        eval_case.expected_nodes == APPROVAL_AGENT_NODES
        for eval_case in dataset.cases
        if eval_case.expected_approval_required
    )


def test_load_agent_eval_dataset_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(EvalDatasetError, match="dataset not found"):
        load_agent_eval_dataset(tmp_path / "missing.jsonl")


def test_load_agent_eval_dataset_rejects_invalid_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "agent_cases.jsonl"
    path.write_text(
        json.dumps({"id": "agent_001"})
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(EvalDatasetError, match="invalid agent eval case"):
        load_agent_eval_dataset(path)
