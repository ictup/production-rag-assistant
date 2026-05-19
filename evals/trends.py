import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from evals.models import EvalCaseType
from evals.runner import EvalRunReport

TrendMetadataValue = str | int | float | bool | None


class EvalTrendDataset(BaseModel):
    name: str
    case_type: EvalCaseType
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float


class EvalTrendRecord(BaseModel):
    recorded_at: datetime
    run_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    datasets: list[EvalTrendDataset]
    failure_reasons: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, TrendMetadataValue] = Field(default_factory=dict)


def count_failure_reasons(report: EvalRunReport) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for result in report.results:
        counts.update(result.failure_reasons)
    return dict(sorted(counts.items()))


def build_eval_trend_record(
    report: EvalRunReport,
    *,
    metadata: dict[str, TrendMetadataValue] | None = None,
    recorded_at: datetime | None = None,
    run_id: str | None = None,
) -> EvalTrendRecord:
    return EvalTrendRecord(
        recorded_at=recorded_at or datetime.now(UTC),
        run_id=run_id or str(uuid.uuid4()),
        total_cases=report.total_cases,
        passed_cases=report.passed_cases,
        failed_cases=report.failed_cases,
        pass_rate=report.pass_rate,
        datasets=[
            EvalTrendDataset(
                name=dataset.name,
                case_type=dataset.case_type,
                total_cases=dataset.total_cases,
                passed_cases=dataset.passed_cases,
                failed_cases=dataset.failed_cases,
                pass_rate=dataset.pass_rate,
            )
            for dataset in report.datasets
        ],
        failure_reasons=count_failure_reasons(report),
        metadata=metadata or {},
    )


def serialize_trend_record(record: EvalTrendRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def write_trend_record(record: EvalTrendRecord, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as file:
        file.write(serialize_trend_record(record) + "\n")
