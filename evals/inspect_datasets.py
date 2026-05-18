import argparse
from pathlib import Path

from evals.loaders import load_default_eval_suite
from evals.models import EvalDataset, EvalSuite


def format_dataset(dataset: EvalDataset) -> list[str]:
    case_ids = ", ".join(eval_case.id for eval_case in dataset.cases)
    return [
        f"- {dataset.name}",
        f"  type: {dataset.case_type}",
        f"  path: {dataset.path}",
        f"  cases: {len(dataset.cases)}",
        f"  ids: {case_ids}",
    ]


def format_eval_suite(suite: EvalSuite) -> str:
    lines = [
        f"datasets: {len(suite.datasets)}",
        f"total cases: {suite.total_cases}",
    ]
    for dataset in suite.datasets:
        lines.extend(format_dataset(dataset))
    return "\n".join(lines)


def validate_eval_suite(
    suite: EvalSuite,
    *,
    min_total_cases: int,
) -> None:
    if suite.total_cases < min_total_cases:
        raise SystemExit(
            "eval dataset check failed: "
            f"cases {suite.total_cases} < required {min_total_cases}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect deterministic eval datasets.")
    parser.add_argument("--datasets-dir", type=Path, default=Path("evals/datasets"))
    parser.add_argument("--min-total-cases", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    suite = load_default_eval_suite(args.datasets_dir)
    print(format_eval_suite(suite))
    validate_eval_suite(suite, min_total_cases=args.min_total_cases)


if __name__ == "__main__":
    main()
