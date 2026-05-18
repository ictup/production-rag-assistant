import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evals.models import EvalCase, EvalCaseType, EvalDataset, EvalSuite

DEFAULT_DATASET_SPECS: tuple[tuple[str, str, EvalCaseType], ...] = (
    ("rag_eval_questions", "rag_eval_questions.jsonl", "rag"),
    ("refusal_questions", "refusal_questions.jsonl", "refusal"),
    ("security_questions", "security_questions.jsonl", "security"),
)


class EvalDatasetError(ValueError):
    pass


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalDatasetError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise EvalDatasetError(f"{path}:{line_number}: expected JSON object")
        rows.append(row)
    return rows


def parse_eval_case(raw_case: dict[str, Any], *, case_type: EvalCaseType) -> EvalCase:
    try:
        return EvalCase.model_validate({**raw_case, "case_type": case_type})
    except ValidationError as exc:
        case_id = raw_case.get("id", "<missing id>")
        raise EvalDatasetError(f"invalid eval case {case_id}: {exc}") from exc


def load_eval_dataset(
    *,
    name: str,
    path: Path,
    case_type: EvalCaseType,
) -> EvalDataset:
    if not path.exists():
        raise EvalDatasetError(f"dataset not found: {path}")

    cases = [
        parse_eval_case(raw_case, case_type=case_type)
        for raw_case in read_jsonl(path)
    ]
    if not cases:
        raise EvalDatasetError(f"dataset is empty: {path}")

    return EvalDataset(
        name=name,
        case_type=case_type,
        path=path,
        cases=cases,
    )


def load_default_eval_suite(
    datasets_dir: Path = Path("evals/datasets"),
) -> EvalSuite:
    return EvalSuite(
        datasets=[
            load_eval_dataset(
                name=name,
                path=datasets_dir / filename,
                case_type=case_type,
            )
            for name, filename, case_type in DEFAULT_DATASET_SPECS
        ]
    )
