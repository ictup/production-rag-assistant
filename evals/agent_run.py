import argparse
import asyncio
import json
from pathlib import Path

from evals.agent_loaders import (
    DEFAULT_AGENT_EVAL_DATASET,
    load_agent_eval_dataset,
)
from evals.agent_runner import AgentEvalRunReport, run_agent_eval_dataset

DEFAULT_AGENT_REPORT_OUTPUT = Path("evals/reports/agent_support_triage.json")


def serialize_agent_report(report: AgentEvalRunReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )


def write_agent_report(
    report: AgentEvalRunReport,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialize_agent_report(report) + "\n", encoding="utf-8")


def format_agent_report_summary(report: AgentEvalRunReport) -> str:
    lines = [
        (
            f"agent eval cases: {report.passed_cases}/"
            f"{report.total_cases} passed ({report.pass_rate:.1%})"
        )
    ]
    for dataset in report.datasets:
        lines.append(
            f"- {dataset.name}: {dataset.passed_cases}/"
            f"{dataset.total_cases} passed ({dataset.pass_rate:.1%})"
        )
    status_counts = ", ".join(
        f"{status}={count}"
        for status, count in report.status_counts.items()
    )
    risk_counts = ", ".join(
        f"{risk_level}={count}"
        for risk_level, count in report.risk_counts.items()
    )
    lines.append(f"- statuses: {status_counts}")
    lines.append(f"- risks: {risk_counts}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic Agent support triage evals."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_AGENT_EVAL_DATASET,
        help="Path to the Agent support triage JSONL dataset.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "summary"),
        default="json",
        help="Report format for stdout.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_AGENT_REPORT_OUTPUT,
        help="Path for the full JSON report. Use --no-output to disable.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write a report file.",
    )
    parser.add_argument(
        "--fail-on-failure",
        action="store_true",
        help="Exit with code 1 when any Agent eval case fails.",
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset = load_agent_eval_dataset(args.dataset)
    report = await run_agent_eval_dataset(dataset)

    if not args.no_output:
        write_agent_report(report, args.output)

    if args.format == "json":
        print(serialize_agent_report(report))
    else:
        print(format_agent_report_summary(report))

    if args.fail_on_failure and report.failed_cases:
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
