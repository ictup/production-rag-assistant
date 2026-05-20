import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.schemas.agent import (
    AgentApprovalDecisionRequest,
    AgentApprovalItem,
    AgentApprovalsResponse,
    AgentTriageResponse,
    SupportTicketRequest,
)


def test_support_ticket_request_trims_required_strings() -> None:
    request = SupportTicketRequest(
        ticket_id=" TICKET-1 ",
        customer_message=" How do I debug citations? ",
        workspace_id=" public ",
        metadata=None,
    )

    assert request.ticket_id == "TICKET-1"
    assert request.customer_message == "How do I debug citations?"
    assert request.workspace_id == "public"
    assert request.metadata == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"ticket_id": "", "customer_message": "message"},
        {"ticket_id": "TICKET-1", "customer_message": " "},
        {"ticket_id": "TICKET-1", "customer_message": "message", "metadata": []},
        {"ticket_id": "TICKET-1", "customer_message": "message", "priority": "p0"},
    ],
)
def test_support_ticket_request_rejects_invalid_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SupportTicketRequest(**payload)


def test_agent_triage_response_defaults_to_empty_collections() -> None:
    response = AgentTriageResponse(run_id="run-1", status="finalized")

    assert response.approval_required is False
    assert response.sources == []
    assert response.retrieval_context is None
    assert response.retrieval == {}
    assert response.historical_cases == []
    assert response.cited_source_ids == []
    assert response.cited_case_ids == []
    assert response.tool_calls == []
    assert response.node_runs == []
    assert response.metrics == {}


def test_agent_approval_decision_rejects_blank_feedback() -> None:
    with pytest.raises(ValidationError):
        AgentApprovalDecisionRequest(decision="rejected", human_feedback=" ")


def test_agent_approval_item_serializes_model() -> None:
    approval = SimpleNamespace(
        id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
        run_id="agent_request-1",
        ticket_id="TICKET-1",
        workspace_id="tenant-a",
        request_id="request-1",
        actor_hash="a" * 64,
        status="pending",
        category="data_privacy",
        risk_level="high",
        reason="high-risk support request",
        customer_message="Delete customer prompts.",
        draft_answer="Human review required.",
        tool_calls=[{"tool_name": "risk_check_tool"}],
        node_runs=[{"node_name": "risk_check"}],
        human_feedback=None,
        metadata_={"source": "test"},
        created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        decided_at=None,
    )

    item = AgentApprovalItem.from_model(approval)  # type: ignore[arg-type]

    assert item.id == "77777777-7777-7777-7777-777777777777"
    assert item.status == "pending"
    assert item.risk_level == "high"
    assert item.metadata == {"source": "test"}
    assert item.tool_calls == [{"tool_name": "risk_check_tool"}]
    assert item.node_runs == [{"node_name": "risk_check"}]


def test_agent_approvals_response_wraps_repository_result() -> None:
    approval = SimpleNamespace(
        id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
        run_id="agent_request-1",
        ticket_id="TICKET-1",
        workspace_id="tenant-a",
        request_id="request-1",
        actor_hash="a" * 64,
        status="approved",
        category="data_privacy",
        risk_level="high",
        reason="high-risk support request",
        customer_message="Delete customer prompts.",
        draft_answer="Human review required.",
        tool_calls=[],
        node_runs=[],
        human_feedback="Looks safe.",
        metadata_={},
        created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
        decided_at=datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
    )
    result = SimpleNamespace(total=3, approvals=[approval])

    response = AgentApprovalsResponse.from_result(
        limit=20,
        offset=0,
        result=result,  # type: ignore[arg-type]
    )

    assert response.total == 3
    assert response.count == 1
    assert response.approvals[0].status == "approved"
