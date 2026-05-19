import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.config import Settings
from evals.run import build_parser, build_trend_metadata
from evals.runner import EvalCaseResult, EvalDatasetResult, EvalRunReport
from evals.trends import build_eval_trend_record, write_trend_record


def make_eval_report() -> EvalRunReport:
    return EvalRunReport(
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        pass_rate=0.5,
        datasets=[
            EvalDatasetResult(
                name="rag_eval_questions",
                case_type="rag",
                total_cases=2,
                passed_cases=1,
                failed_cases=1,
                pass_rate=0.5,
            )
        ],
        results=[
            EvalCaseResult(
                dataset_name="rag_eval_questions",
                id="rag_001",
                case_type="rag",
                question="What does FlashAttention reduce?",
                passed=True,
                failure_reasons=[],
                answer="It reduces memory traffic.",
                refused=False,
                refusal_reason=None,
                citation_valid=True,
                source_match=True,
                keyword_match=True,
                refusal_match=None,
                missing_sources=[],
                missing_keywords=[],
                sources=["llm_systems/flashattention.md"],
                retrieval={},
                usage={},
            ),
            EvalCaseResult(
                dataset_name="rag_eval_questions",
                id="rag_002",
                case_type="rag",
                question="Which source explains KV cache?",
                passed=False,
                failure_reasons=[
                    "missing_expected_sources: kv-cache.md",
                    "expected_valid_citation",
                ],
                answer="",
                refused=False,
                refusal_reason=None,
                citation_valid=False,
                source_match=False,
                keyword_match=True,
                refusal_match=None,
                missing_sources=["kv-cache.md"],
                missing_keywords=[],
                sources=[],
                retrieval={},
                usage={},
            ),
        ],
    )


def test_build_eval_trend_record_summarizes_report() -> None:
    recorded_at = datetime(2026, 5, 20, 8, 30, tzinfo=UTC)

    record = build_eval_trend_record(
        make_eval_report(),
        metadata={"workspace_id": "public", "rerank": True},
        recorded_at=recorded_at,
        run_id="run-123",
    )

    assert record.recorded_at == recorded_at
    assert record.run_id == "run-123"
    assert record.total_cases == 2
    assert record.passed_cases == 1
    assert record.failed_cases == 1
    assert record.pass_rate == 0.5
    assert record.datasets[0].name == "rag_eval_questions"
    assert record.datasets[0].case_type == "rag"
    assert record.failure_reasons == {
        "expected_valid_citation": 1,
        "missing_expected_sources: kv-cache.md": 1,
    }
    assert record.metadata == {"workspace_id": "public", "rerank": True}


def test_write_trend_record_appends_jsonl(tmp_path) -> None:
    output_path = tmp_path / "reports" / "trends.jsonl"
    report = make_eval_report()

    write_trend_record(
        build_eval_trend_record(
            report,
            recorded_at=datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
            run_id="run-1",
        ),
        output_path,
    )
    write_trend_record(
        build_eval_trend_record(
            report,
            recorded_at=datetime(2026, 5, 20, 8, 31, tzinfo=UTC),
            run_id="run-2",
        ),
        output_path,
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert [json.loads(line)["run_id"] for line in lines] == ["run-1", "run-2"]
    assert json.loads(lines[0])["failure_reasons"] == {
        "expected_valid_citation": 1,
        "missing_expected_sources: kv-cache.md": 1,
    }


def test_eval_parser_supports_trend_output() -> None:
    args = build_parser().parse_args(
        [
            "--trend-output",
            "evals/reports/trends.jsonl",
        ]
    )

    assert args.trend_output.as_posix() == "evals/reports/trends.jsonl"


def test_build_trend_metadata_captures_runtime_settings() -> None:
    args = build_parser().parse_args(
        [
            "--datasets-dir",
            "evals/custom",
            "--workspace-id",
            "tenant-a",
            "--vector-top-k",
            "7",
            "--sparse-top-k",
            "8",
            "--fused-top-k",
            "9",
            "--rerank-top-n",
            "3",
            "--no-rerank",
        ]
    )
    settings = Settings(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        generator_provider="openai",
        llm_model="gpt-test",
        openai_api_key="test-key",
        openai_max_output_tokens=321,
    )

    metadata = build_trend_metadata(args=args, settings=settings)

    assert metadata == {
        "datasets_dir": "evals/custom",
        "workspace_id": "tenant-a",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "generator_provider": "openai",
        "llm_model": "gpt-test",
        "vector_top_k": 7,
        "sparse_top_k": 8,
        "fused_top_k": 9,
        "rerank_top_n": 3,
        "rerank": False,
        "openai_max_output_tokens": 321,
    }


def test_makefile_exposes_eval_trend_target() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "eval-trend:" in makefile
    assert "--trend-output evals/reports/trends.jsonl" in makefile


def test_eval_trends_doc_is_linked_from_readme_and_handoff() -> None:
    assert "docs/EVAL_TRENDS.md" in Path("README.md").read_text(encoding="utf-8")
    assert "docs/EVAL_TRENDS.md" in Path("docs/PROJECT_HANDOFF.md").read_text(
        encoding="utf-8"
    )
