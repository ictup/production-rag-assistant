import uuid
from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from backend.app.agent.workflow import run_support_triage_skeleton
from backend.app.db.repositories import SupportTicketSummary
from backend.app.rag.citations import Source
from backend.app.rag.pipeline import RagRetrievalContext, RetrievalInfo
from backend.app.schemas.agent import AgentTriageResponse
from evals.agent_models import AgentEvalCase, AgentEvalDataset
from evals.runner import calculate_pass_rate, count_failed, count_passed


class AgentEvalCaseResult(BaseModel):
    dataset_name: str
    id: str
    ticket_id: str
    passed: bool
    failure_reasons: list[str]
    status: str
    category: str | None
    risk_level: str | None
    approval_required: bool
    approval_id: str | None
    expected_status: str
    expected_category: str
    expected_risk_level: str
    expected_approval_required: bool
    node_match: bool
    tool_match: bool
    answer_keyword_match: bool | None
    reason_keyword_match: bool | None
    citation_valid: bool | None
    node_names: list[str]
    tool_names: list[str]
    answer: str
    reason: str | None
    metrics: dict[str, Any]


class AgentEvalDatasetResult(BaseModel):
    name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float


class AgentEvalRunReport(BaseModel):
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    datasets: list[AgentEvalDatasetResult]
    status_counts: dict[str, int]
    category_counts: dict[str, int]
    risk_counts: dict[str, int]
    results: list[AgentEvalCaseResult]


class AgentEvalRagPipeline:
    async def retrieve_context(self, request: object) -> RagRetrievalContext:
        query = getattr(request, "question", "")
        return RagRetrievalContext(
            sources=[
                Source(
                    source_id="1",
                    title="Support Triage Runbook",
                    section="Agent Evaluation",
                    source_uri="docs/support_triage_runbook.md",
                    chunk_id="agent-eval-source-1",
                    score=0.91,
                )
            ],
            context=(
                "[1] Support Triage Runbook\n"
                "Use request id, workspace id, retrieved chunks, citation "
                "validation, p95 latency, quota, migration state, deployment "
                f"configuration, and eval traces. Query: {query}"
            ),
            retrieval=RetrievalInfo(
                mode="hybrid_rrf_rerank",
                vector_top_k=5,
                sparse_top_k=5,
                fused_count=1,
                used_count=1,
                top_score=0.91,
            ),
        )


class AgentEvalSupportTicketRepository:
    async def list_similar_support_tickets(
        self,
        **kwargs: object,
    ) -> list[SupportTicketSummary]:
        category = str(kwargs.get("category") or "unknown")
        return [
            SupportTicketSummary(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"agent-eval:{category}"),
                ticket_id=f"HIST-{category.upper()}-001",
                workspace_id=str(kwargs.get("workspace_id") or "public"),
                category=category,
                customer_message=f"Prior {category} support case.",
                resolution_summary=(
                    "Captured request id, workspace id, traces, retrieved "
                    "sources, and the final operator decision."
                ),
                final_response=None,
                tags=["agent-eval", category],
                risk_level=None,
                metadata={"source": "agent_eval"},
                created_at=datetime(2026, 5, 21, 0, 0, tzinfo=UTC),
            )
        ]


class AgentEvalApprovalRepository:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []

    async def create_agent_approval(self, approval_input: object, **kwargs: object):
        self.create_calls.append(
            {
                "approval_input": approval_input,
                **kwargs,
            }
        )
        run_id = approval_input.run_id  # type: ignore[attr-defined]
        approval_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"agent-eval:{run_id}",
        )
        return SimpleNamespace(id=approval_id)


async def run_agent_eval_dataset(
    dataset: AgentEvalDataset,
) -> AgentEvalRunReport:
    results: list[AgentEvalCaseResult] = []
    for eval_case in dataset.cases:
        try:
            response = await run_agent_eval_case(eval_case)
        except Exception as exc:  # noqa: BLE001
            results.append(
                build_error_result(
                    eval_case,
                    dataset_name=dataset.name,
                    exc=exc,
                )
            )
            continue
        results.append(
            score_agent_eval_case(
                eval_case,
                response=response,
                dataset_name=dataset.name,
            )
        )
    return build_agent_eval_report(dataset, results)


async def run_agent_eval_case(eval_case: AgentEvalCase) -> AgentTriageResponse:
    return await run_support_triage_skeleton(
        eval_case.to_request(),
        rag_pipeline=AgentEvalRagPipeline(),  # type: ignore[arg-type]
        support_ticket_repository=AgentEvalSupportTicketRepository(),  # type: ignore[arg-type]
        agent_approval_repository=AgentEvalApprovalRepository(),  # type: ignore[arg-type]
        actor_hash="agent-eval",
        request_id=f"agent-eval-{eval_case.id}",
        trace_id=f"agent-eval-trace-{eval_case.id}",
    )


def score_agent_eval_case(
    eval_case: AgentEvalCase,
    *,
    response: AgentTriageResponse,
    dataset_name: str,
) -> AgentEvalCaseResult:
    failure_reasons: list[str] = []
    node_names = [str(node_run.get("node_name")) for node_run in response.node_runs]
    tool_names = [str(tool_call.get("tool_name")) for tool_call in response.tool_calls]
    answer = response.final_answer or response.draft_answer or ""
    reason = response.reason

    if response.status != eval_case.expected_status:
        failure_reasons.append(
            "status_mismatch: expected "
            f"{eval_case.expected_status}, got {response.status}"
        )
    if response.category != eval_case.expected_category:
        failure_reasons.append(
            "category_mismatch: expected "
            f"{eval_case.expected_category}, got {response.category}"
        )
    if response.risk_level != eval_case.expected_risk_level:
        failure_reasons.append(
            "risk_level_mismatch: expected "
            f"{eval_case.expected_risk_level}, got {response.risk_level}"
        )
    if response.approval_required != eval_case.expected_approval_required:
        failure_reasons.append(
            "approval_required_mismatch: expected "
            f"{eval_case.expected_approval_required}, got {response.approval_required}"
        )
    if eval_case.expected_approval_required and response.approval_id is None:
        failure_reasons.append("expected_approval_id")

    node_match = node_names == eval_case.expected_nodes
    if not node_match:
        failure_reasons.append(
            "node_sequence_mismatch: expected "
            f"{eval_case.expected_nodes}, got {node_names}"
        )

    tool_match = tool_names == eval_case.expected_tools
    if not tool_match:
        failure_reasons.append(
            "tool_sequence_mismatch: expected "
            f"{eval_case.expected_tools}, got {tool_names}"
        )

    answer_keyword_match = None
    if eval_case.expected_answer_keywords:
        missing_answer_keywords = find_missing_keywords(
            eval_case.expected_answer_keywords,
            answer,
        )
        answer_keyword_match = not missing_answer_keywords
        if missing_answer_keywords:
            failure_reasons.append(
                "missing_answer_keywords: " + ", ".join(missing_answer_keywords)
            )

    reason_keyword_match = None
    if eval_case.expected_reason_keywords:
        missing_reason_keywords = find_missing_keywords(
            eval_case.expected_reason_keywords,
            reason or "",
        )
        reason_keyword_match = not missing_reason_keywords
        if missing_reason_keywords:
            failure_reasons.append(
                "missing_reason_keywords: " + ", ".join(missing_reason_keywords)
            )

    citation_valid = response.metrics.get("citation_valid")
    if citation_valid is not None and not isinstance(citation_valid, bool):
        citation_valid = None
    if (
        eval_case.expected_citation_valid is not None
        and citation_valid != eval_case.expected_citation_valid
    ):
        failure_reasons.append(
            "citation_valid_mismatch: expected "
            f"{eval_case.expected_citation_valid}, got {citation_valid}"
        )

    return AgentEvalCaseResult(
        dataset_name=dataset_name,
        id=eval_case.id,
        ticket_id=eval_case.ticket_id or eval_case.id,
        passed=not failure_reasons,
        failure_reasons=failure_reasons,
        status=response.status,
        category=response.category,
        risk_level=response.risk_level,
        approval_required=response.approval_required,
        approval_id=response.approval_id,
        expected_status=eval_case.expected_status,
        expected_category=eval_case.expected_category,
        expected_risk_level=eval_case.expected_risk_level,
        expected_approval_required=eval_case.expected_approval_required,
        node_match=node_match,
        tool_match=tool_match,
        answer_keyword_match=answer_keyword_match,
        reason_keyword_match=reason_keyword_match,
        citation_valid=citation_valid,
        node_names=node_names,
        tool_names=tool_names,
        answer=answer,
        reason=reason,
        metrics=response.metrics,
    )


def build_error_result(
    eval_case: AgentEvalCase,
    *,
    dataset_name: str,
    exc: Exception,
) -> AgentEvalCaseResult:
    return AgentEvalCaseResult(
        dataset_name=dataset_name,
        id=eval_case.id,
        ticket_id=eval_case.ticket_id or eval_case.id,
        passed=False,
        failure_reasons=[f"runner_error: {type(exc).__name__}: {exc}"],
        status="failed",
        category=None,
        risk_level=None,
        approval_required=False,
        approval_id=None,
        expected_status=eval_case.expected_status,
        expected_category=eval_case.expected_category,
        expected_risk_level=eval_case.expected_risk_level,
        expected_approval_required=eval_case.expected_approval_required,
        node_match=False,
        tool_match=False,
        answer_keyword_match=None,
        reason_keyword_match=None,
        citation_valid=None,
        node_names=[],
        tool_names=[],
        answer="",
        reason=None,
        metrics={},
    )


def build_agent_eval_report(
    dataset: AgentEvalDataset,
    results: list[AgentEvalCaseResult],
) -> AgentEvalRunReport:
    dataset_result = AgentEvalDatasetResult(
        name=dataset.name,
        total_cases=len(results),
        passed_cases=count_passed(results),
        failed_cases=count_failed(results),
        pass_rate=calculate_pass_rate(results),
    )
    return AgentEvalRunReport(
        total_cases=len(results),
        passed_cases=count_passed(results),
        failed_cases=count_failed(results),
        pass_rate=calculate_pass_rate(results),
        datasets=[dataset_result],
        status_counts=count_result_field(results, "status"),
        category_counts=count_result_field(results, "category"),
        risk_counts=count_result_field(results, "risk_level"),
        results=results,
    )


def count_result_field(
    results: list[AgentEvalCaseResult],
    field_name: str,
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for result in results:
        value = getattr(result, field_name)
        counter[str(value or "unknown")] += 1
    return dict(sorted(counter.items()))


def find_missing_keywords(expected_keywords: list[str], value: str) -> list[str]:
    normalized_value = value.casefold()
    return [
        keyword
        for keyword in expected_keywords
        if keyword.casefold() not in normalized_value
    ]
