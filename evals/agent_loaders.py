from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evals.agent_models import AgentEvalCase, AgentEvalDataset
from evals.loaders import EvalDatasetError, read_jsonl

DEFAULT_AGENT_EVAL_DATASET = Path("evals/datasets/agent_support_triage.jsonl")
DEFAULT_AGENT_EVAL_DATASET_NAME = "agent_support_triage"


def parse_agent_eval_case(raw_case: dict[str, Any]) -> AgentEvalCase:
    try:
        return AgentEvalCase.model_validate(raw_case)
    except ValidationError as exc:
        case_id = raw_case.get("id", "<missing id>")
        raise EvalDatasetError(f"invalid agent eval case {case_id}: {exc}") from exc


def load_agent_eval_dataset(
    path: Path = DEFAULT_AGENT_EVAL_DATASET,
    *,
    name: str = DEFAULT_AGENT_EVAL_DATASET_NAME,
) -> AgentEvalDataset:
    if not path.exists():
        raise EvalDatasetError(f"dataset not found: {path}")

    cases = [parse_agent_eval_case(raw_case) for raw_case in read_jsonl(path)]
    if not cases:
        raise EvalDatasetError(f"dataset is empty: {path}")

    return AgentEvalDataset(name=name, path=path, cases=cases)
