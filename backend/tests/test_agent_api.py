import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.api import routes_agent
from backend.app.core.config import Settings, get_settings
from backend.app.main import create_app
from backend.app.rag.citations import Source
from backend.app.rag.pipeline import RagRetrievalContext, RetrievalInfo

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class FakeRagPipeline:
    def __init__(self) -> None:
        self.requests = []

    async def retrieve_context(self, request):
        self.requests.append(request)
        return RagRetrievalContext(
            sources=[
                Source(
                    source_id="1",
                    title="Citation Debugging",
                    section="Validation",
                    source_uri="docs/citations.md",
                    chunk_id="chunk-1",
                    score=0.92,
                )
            ],
            context="[1] Citation Debugging\nInspect retrieved chunks.",
            retrieval=RetrievalInfo(
                mode="hybrid_rrf_rerank",
                vector_top_k=5,
                sparse_top_k=5,
                fused_count=1,
                used_count=1,
                top_score=0.92,
            ),
        )


class FakeSupportTicketRepository:
    def __init__(self) -> None:
        self.calls = []

    async def list_similar_support_tickets(self, **kwargs):
        self.calls.append(dict(kwargs))
        return []


def make_agent_approval(status: str = "pending"):
    decided_at = (
        datetime(2026, 5, 20, 8, 30, tzinfo=UTC)
        if status != "pending"
        else None
    )
    return SimpleNamespace(
        id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
        run_id="agent_request-1",
        ticket_id="TICKET-1",
        workspace_id="tenant-a",
        request_id="request-1",
        actor_hash="a" * 64,
        status=status,
        category="data_privacy",
        risk_level="high",
        reason="high-risk support request",
        customer_message="Delete customer prompts.",
        draft_answer="This support request requires human review.",
        tool_calls=[{"tool_name": "risk_check_tool"}],
        node_runs=[{"node_name": "risk_check"}],
        human_feedback="Reviewed." if status != "pending" else None,
        metadata_={"source": "test"},
        created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
        decided_at=decided_at,
    )


MISSING = object()


class FakeAgentApprovalRepository:
    def __init__(
        self,
        approval=MISSING,
        total: int = 1,
        decision_error: ValueError | None = None,
    ) -> None:
        self.approval = make_agent_approval() if approval is MISSING else approval
        self.total = total
        self.decision_error = decision_error
        self.list_calls = []
        self.get_calls = []
        self.decision_calls = []

    async def list_agent_approvals(self, **kwargs):
        self.list_calls.append(dict(kwargs))
        approvals = [] if self.approval is None else [self.approval]
        return SimpleNamespace(total=self.total, approvals=approvals)

    async def get_agent_approval(self, **kwargs):
        self.get_calls.append(dict(kwargs))
        return self.approval

    async def decide_agent_approval(self, **kwargs):
        self.decision_calls.append(dict(kwargs))
        if self.decision_error is not None:
            raise self.decision_error
        if self.approval is None:
            return None
        self.approval.status = kwargs["decision"]
        self.approval.human_feedback = kwargs.get("human_feedback")
        self.approval.decided_at = datetime(2026, 5, 20, 8, 45, tzinfo=UTC)
        self.approval.updated_at = self.approval.decided_at
        return self.approval


class FakeWorkspaceRepository:
    def __init__(
        self,
        workspace_ids: set[str] | None = None,
        archived_workspace_ids: set[str] | None = None,
    ) -> None:
        self.workspace_ids = workspace_ids or {"public", "tenant-a"}
        self.archived_workspace_ids = archived_workspace_ids or set()

    async def get_workspace(self, *, workspace_id: str):
        if workspace_id not in self.workspace_ids:
            return None
        archived_at = (
            datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
            if workspace_id in self.archived_workspace_ids
            else None
        )
        return SimpleNamespace(id=workspace_id, archived_at=archived_at)


def build_client(
    settings: Settings | None = None,
    fake_pipeline: FakeRagPipeline | None = None,
    fake_ticket_repository: FakeSupportTicketRepository | None = None,
    fake_approval_repository: FakeAgentApprovalRepository | None = None,
    fake_workspace_repository: FakeWorkspaceRepository | None = None,
) -> TestClient:
    settings = settings or Settings(api_keys="dev-key")
    fake_pipeline = fake_pipeline or FakeRagPipeline()
    fake_ticket_repository = fake_ticket_repository or FakeSupportTicketRepository()
    fake_approval_repository = (
        fake_approval_repository or FakeAgentApprovalRepository()
    )
    fake_workspace_repository = (
        fake_workspace_repository or FakeWorkspaceRepository()
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_agent.get_agent_rag_pipeline] = (
        lambda: fake_pipeline
    )
    app.dependency_overrides[routes_agent.get_support_ticket_repository] = (
        lambda: fake_ticket_repository
    )
    app.dependency_overrides[routes_agent.get_agent_approval_repository] = (
        lambda: fake_approval_repository
    )
    app.dependency_overrides[routes_agent.get_workspace_repository] = (
        lambda: fake_workspace_repository
    )
    return TestClient(app)


def test_support_triage_route_returns_finalized_skeleton_response() -> None:
    fake_pipeline = FakeRagPipeline()
    fake_ticket_repository = FakeSupportTicketRepository()
    client = build_client(
        fake_pipeline=fake_pipeline,
        fake_ticket_repository=fake_ticket_repository,
    )

    response = client.post(
        "/agent/support-triage",
        headers={
            **AUTH_HEADERS,
            "X-Request-ID": "request-1",
            "X-Trace-ID": "trace-1",
        },
        json={
            "ticket_id": "TICKET-1",
            "customer_message": "How can I debug citation validation failures?",
            "workspace_id": " public ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "agent_request-1"
    assert body["status"] == "finalized"
    assert body["category"] == "rag_failure"
    assert body["risk_level"] == "low"
    assert body["approval_required"] is False
    assert body["draft_answer"] == body["final_answer"]
    assert "Citation Debugging" in body["final_answer"]
    assert "[1]" in body["final_answer"]
    assert body["trace_id"] == "trace-1"
    assert body["sources"][0]["chunk_id"] == "chunk-1"
    assert body["retrieval_context"] == (
        "[1] Citation Debugging\nInspect retrieved chunks."
    )
    assert body["retrieval"]["top_score"] == 0.92
    assert body["historical_cases"] == []
    assert body["cited_source_ids"] == ["1"]
    assert body["cited_case_ids"] == []
    assert body["metrics"]["tool_count"] == 5
    assert body["metrics"]["citation_valid"] is True
    assert body["metrics"]["retrieved_source_count"] == 1
    assert body["metrics"]["historical_case_count"] == 0
    assert body["metrics"]["cited_source_count"] == 1
    assert body["metrics"]["cited_case_count"] == 0
    assert body["metrics"]["node_count"] == 5
    assert [tool_call["tool_name"] for tool_call in body["tool_calls"]] == [
        "classify_ticket_tool",
        "risk_check_tool",
        "rag_search_tool",
        "ticket_lookup_tool",
        "draft_response_tool",
    ]
    assert [node_run["node_name"] for node_run in body["node_runs"]] == [
        "classify_ticket",
        "risk_check",
        "rag_search",
        "ticket_lookup",
        "draft_response",
    ]
    assert all(node_run["success"] for node_run in body["node_runs"])
    assert len(fake_pipeline.requests) == 1
    assert fake_pipeline.requests[0].workspace_id == "public"
    assert fake_ticket_repository.calls == [
        {
            "query": "How can I debug citation validation failures?",
            "workspace_id": "public",
            "category": "rag_failure",
            "limit": 5,
        }
    ]


def test_support_triage_route_returns_approval_required_for_high_risk_ticket() -> None:
    fake_pipeline = FakeRagPipeline()
    fake_ticket_repository = FakeSupportTicketRepository()
    client = build_client(
        fake_pipeline=fake_pipeline,
        fake_ticket_repository=fake_ticket_repository,
    )

    response = client.post(
        "/agent/support-triage",
        headers=AUTH_HEADERS,
        json={
            "ticket_id": "TICKET-2",
            "customer_message": (
                "Delete all logs that contain customer prompts from production."
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approval_required"
    assert body["category"] == "data_privacy"
    assert body["risk_level"] == "high"
    assert body["approval_required"] is True
    assert body["approval_id"] is None
    assert body["draft_answer"] is not None
    assert body["final_answer"] is None
    assert body["sources"] == []
    assert body["retrieval"] == {}
    assert body["historical_cases"] == []
    assert body["cited_source_ids"] == []
    assert body["cited_case_ids"] == []
    assert body["metrics"]["node_count"] == 2
    assert [node_run["node_name"] for node_run in body["node_runs"]] == [
        "classify_ticket",
        "risk_check",
    ]
    assert fake_pipeline.requests == []
    assert fake_ticket_repository.calls == []


def test_support_triage_route_requires_api_key() -> None:
    client = build_client()

    response = client.post(
        "/agent/support-triage",
        json={
            "ticket_id": "TICKET-1",
            "customer_message": "How can I debug citations?",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "missing api key"


def test_support_triage_route_enforces_workspace_access() -> None:
    client = build_client(
        Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        )
    )

    response = client.post(
        "/agent/support-triage",
        headers={"Authorization": "Bearer tenant-key"},
        json={
            "ticket_id": "TICKET-1",
            "customer_message": "How can I debug citations?",
            "workspace_id": "tenant-b",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "workspace access denied"


def test_openapi_exposes_support_triage_route() -> None:
    client = build_client()

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/agent/support-triage" in paths
    assert "/agent/approvals" in paths
    assert "/agent/approvals/{approval_id}" in paths
    assert "/agent/approvals/{approval_id}/decision" in paths


def test_list_agent_approvals_filters_workspace_and_status() -> None:
    fake_repository = FakeAgentApprovalRepository()
    client = build_client(
        Settings(
            api_keys="operator-key",
            api_key_roles="operator-key=operator",
            api_key_workspace_access="operator-key=tenant-a",
        ),
        fake_approval_repository=fake_repository,
    )

    response = client.get(
        "/agent/approvals?workspace_id=tenant-a&status=pending&limit=10&offset=5",
        headers={"Authorization": "Bearer operator-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["approvals"][0]["id"] == "77777777-7777-7777-7777-777777777777"
    assert body["approvals"][0]["workspace_id"] == "tenant-a"
    assert body["approvals"][0]["status"] == "pending"
    assert body["approvals"][0]["tool_calls"] == [
        {"tool_name": "risk_check_tool"}
    ]
    assert body["approvals"][0]["node_runs"] == [
        {"node_name": "risk_check"}
    ]
    assert fake_repository.list_calls == [
        {
            "workspace_id": "tenant-a",
            "status": "pending",
            "limit": 10,
            "offset": 5,
        }
    ]


def test_list_agent_approvals_enforces_operator_role() -> None:
    client = build_client(
        Settings(
            api_keys="viewer-key",
            api_key_roles="viewer-key=viewer",
        )
    )

    response = client.get(
        "/agent/approvals",
        headers={"Authorization": "Bearer viewer-key"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient api role"


def test_get_agent_approval_returns_detail() -> None:
    fake_repository = FakeAgentApprovalRepository()
    client = build_client(
        Settings(
            api_keys="operator-key",
            api_key_roles="operator-key=operator",
        ),
        fake_approval_repository=fake_repository,
    )

    response = client.get(
        "/agent/approvals/77777777-7777-7777-7777-777777777777"
        "?workspace_id=tenant-a",
        headers={"Authorization": "Bearer operator-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval"]["run_id"] == "agent_request-1"
    assert body["approval"]["ticket_id"] == "TICKET-1"
    assert body["approval"]["metadata"] == {"source": "test"}
    assert fake_repository.get_calls == [
        {
            "approval_id": uuid.UUID("77777777-7777-7777-7777-777777777777"),
            "workspace_id": "tenant-a",
        }
    ]


def test_get_agent_approval_returns_404_when_missing() -> None:
    fake_repository = FakeAgentApprovalRepository(approval=None, total=0)
    client = build_client(
        Settings(
            api_keys="operator-key",
            api_key_roles="operator-key=operator",
        ),
        fake_approval_repository=fake_repository,
    )

    response = client.get(
        "/agent/approvals/77777777-7777-7777-7777-777777777777",
        headers={"Authorization": "Bearer operator-key"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "agent approval not found"


def test_decide_agent_approval_updates_pending_approval() -> None:
    fake_repository = FakeAgentApprovalRepository()
    client = build_client(
        Settings(
            api_keys="admin-key",
            api_key_roles="admin-key=admin",
            api_key_workspace_access="admin-key=tenant-a",
        ),
        fake_approval_repository=fake_repository,
    )

    response = client.post(
        "/agent/approvals/77777777-7777-7777-7777-777777777777/decision"
        "?workspace_id=tenant-a",
        headers={"Authorization": "Bearer admin-key"},
        json={
            "decision": "approved",
            "human_feedback": "Looks safe.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval"]["status"] == "approved"
    assert body["approval"]["human_feedback"] == "Looks safe."
    assert body["approval"]["decided_at"] is not None
    assert fake_repository.decision_calls == [
        {
            "approval_id": uuid.UUID("77777777-7777-7777-7777-777777777777"),
            "workspace_id": "tenant-a",
            "decision": "approved",
            "human_feedback": "Looks safe.",
            "commit": True,
        }
    ]


def test_decide_agent_approval_requires_admin_role() -> None:
    client = build_client(
        Settings(
            api_keys="operator-key",
            api_key_roles="operator-key=operator",
        )
    )

    response = client.post(
        "/agent/approvals/77777777-7777-7777-7777-777777777777/decision",
        headers={"Authorization": "Bearer operator-key"},
        json={"decision": "approved"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient api role"


def test_decide_agent_approval_returns_409_when_not_pending() -> None:
    fake_repository = FakeAgentApprovalRepository(
        decision_error=ValueError("agent approval must be pending to decide")
    )
    client = build_client(fake_approval_repository=fake_repository)

    response = client.post(
        "/agent/approvals/77777777-7777-7777-7777-777777777777/decision",
        headers=AUTH_HEADERS,
        json={"decision": "rejected"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "agent approval is not pending"
