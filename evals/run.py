import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_sessionmaker
from backend.app.rag.pipeline import ChatPipelineRequest, RagPipeline
from evals.loaders import load_default_eval_suite
from evals.models import EvalCase
from evals.runner import EvalRunReport, run_eval_suite
from evals.trends import (
    TrendMetadataValue,
    build_eval_trend_record,
    write_trend_record,
)

DEFAULT_REPORT_OUTPUT = Path("evals/reports/latest.json")
DEFAULT_TREND_OUTPUT = Path("evals/reports/trends.jsonl")
ProviderName = Literal["fake", "openai"]


def serialize_report(report: EvalRunReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )


def write_report(report: EvalRunReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialize_report(report) + "\n", encoding="utf-8")


def format_report_summary(report: EvalRunReport) -> str:
    lines = [
        (
            f"eval cases: {report.passed_cases}/{report.total_cases} passed "
            f"({report.pass_rate:.1%})"
        )
    ]
    for dataset in report.datasets:
        lines.append(
            f"- {dataset.name}: {dataset.passed_cases}/"
            f"{dataset.total_cases} passed ({dataset.pass_rate:.1%})"
        )
    return "\n".join(lines)


def build_eval_settings(
    settings: Settings | None = None,
    *,
    embedding_provider: ProviderName | None = None,
    generator_provider: ProviderName | None = None,
    llm_model: str | None = None,
    openai_max_output_tokens: int | None = None,
) -> Settings:
    settings = settings or get_settings()
    updates = {}
    if embedding_provider is not None:
        updates["embedding_provider"] = embedding_provider
    if generator_provider is not None:
        updates["generator_provider"] = generator_provider
    if llm_model is not None:
        updates["llm_model"] = llm_model
    if openai_max_output_tokens is not None:
        if openai_max_output_tokens <= 0:
            raise ValueError("openai_max_output_tokens must be greater than zero")
        updates["openai_max_output_tokens"] = openai_max_output_tokens

    if not updates:
        return settings
    return Settings(**{**settings.model_dump(), **updates})


def build_trend_metadata(
    *,
    args: argparse.Namespace,
    settings: Settings,
) -> dict[str, TrendMetadataValue]:
    return {
        "datasets_dir": args.datasets_dir.as_posix(),
        "workspace_id": args.workspace_id,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "generator_provider": settings.generator_provider,
        "llm_model": settings.llm_model,
        "vector_top_k": args.vector_top_k,
        "sparse_top_k": args.sparse_top_k,
        "fused_top_k": args.fused_top_k,
        "rerank_top_n": args.rerank_top_n,
        "rerank": not args.no_rerank,
        "openai_max_output_tokens": settings.openai_max_output_tokens,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic RAG evals.")
    parser.add_argument("--datasets-dir", type=Path, default=Path("evals/datasets"))
    parser.add_argument("--workspace-id", default="public")
    parser.add_argument("--vector-top-k", type=int, default=5)
    parser.add_argument("--sparse-top-k", type=int, default=5)
    parser.add_argument("--fused-top-k", type=int, default=5)
    parser.add_argument("--rerank-top-n", type=int, default=2)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument(
        "--embedding-provider",
        choices=["fake", "openai"],
        default=None,
        help="Override EMBEDDING_PROVIDER for this eval run.",
    )
    parser.add_argument(
        "--generator-provider",
        choices=["fake", "openai"],
        default=None,
        help="Override GENERATOR_PROVIDER for this eval run.",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="Override LLM_MODEL for this eval run.",
    )
    parser.add_argument(
        "--openai-max-output-tokens",
        type=int,
        default=None,
        help="Override OPENAI_MAX_OUTPUT_TOKENS for this eval run.",
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
        default=DEFAULT_REPORT_OUTPUT,
        help="Path for the full JSON report. Use --no-output to disable.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write a report file.",
    )
    parser.add_argument(
        "--trend-output",
        type=Path,
        default=None,
        help=(
            "Append a compact JSONL trend record to this path. "
            f"Suggested default: {DEFAULT_TREND_OUTPUT}"
        ),
    )
    parser.add_argument(
        "--fail-on-failure",
        action="store_true",
        help="Exit with code 1 when any eval case fails.",
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    suite = load_default_eval_suite(args.datasets_dir)
    sessionmaker = get_sessionmaker()
    settings = build_eval_settings(
        embedding_provider=args.embedding_provider,
        generator_provider=args.generator_provider,
        llm_model=args.llm_model,
        openai_max_output_tokens=args.openai_max_output_tokens,
    )

    async with sessionmaker() as session:
        pipeline = RagPipeline(session=session, settings=settings)

        async def answer_case(eval_case: EvalCase):
            return await pipeline.answer_question(
                ChatPipelineRequest(
                    question=eval_case.question,
                    workspace_id=args.workspace_id,
                    vector_top_k=args.vector_top_k,
                    sparse_top_k=args.sparse_top_k,
                    fused_top_k=args.fused_top_k,
                    rerank_top_n=args.rerank_top_n,
                    rerank=not args.no_rerank,
                )
            )

        report = await run_eval_suite(suite, answer_case=answer_case)

    if not args.no_output:
        write_report(report, args.output)

    if args.trend_output is not None:
        write_trend_record(
            build_eval_trend_record(
                report,
                metadata=build_trend_metadata(args=args, settings=settings),
            ),
            args.trend_output,
        )

    if args.format == "json":
        print(serialize_report(report))
    else:
        print(format_report_summary(report))

    if args.fail_on_failure and report.failed_cases:
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
