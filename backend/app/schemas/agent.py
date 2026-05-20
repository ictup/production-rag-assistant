from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.agent.state import (
    AgentState,
    RiskLevel,
    TicketCategory,
    build_initial_agent_state,
)
from backend.app.db.models import AgentApproval
from backend.app.db.repositories import AgentApprovalListResult

TicketPriority = Literal["low", "normal", "high", "urgent"]
CustomerTier = Literal["free", "pro", "enterprise"]
AgentRunStatus = Literal["finalized", "approval_required", "failed"]
ApprovalDecision = Literal["approved", "rejected"]
AgentApprovalStatus = Literal["pending", "approved", "rejected"]


class SupportTicketRequest(BaseModel):
    ticket_id: str
    customer_message: str
    priority: TicketPriority = "normal"
    workspace_id: str = "public"
    customer_tier: CustomerTier | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ticket_id", "customer_message", "workspace_id")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def metadata_must_be_object(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("metadata must be an object")
        return dict(value)

    def to_initial_state(self, *, run_id: str) -> AgentState:
        return build_initial_agent_state(
            run_id=run_id,
            ticket_id=self.ticket_id,
            customer_message=self.customer_message,
            priority=self.priority,
            workspace_id=self.workspace_id,
            customer_tier=self.customer_tier,
            metadata=self.metadata,
        )


class AgentTriageResponse(BaseModel):
    run_id: str
    status: AgentRunStatus
    category: TicketCategory | None = None
    risk_level: RiskLevel | None = None
    approval_required: bool = False
    approval_id: str | None = None
    final_answer: str | None = None
    draft_answer: str | None = None
    reason: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_context: str | None = None
    retrieval: dict[str, Any] = Field(default_factory=dict)
    historical_cases: list[dict[str, Any]] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)
    cited_case_ids: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    node_runs: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


class AgentApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    human_feedback: str | None = None

    @field_validator("human_feedback")
    @classmethod
    def human_feedback_must_not_be_blank(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("human_feedback must not be blank")
        return value


class AgentApprovalItem(BaseModel):
    id: str
    run_id: str
    ticket_id: str
    workspace_id: str
    request_id: str
    actor_hash: str
    status: AgentApprovalStatus
    category: str | None
    risk_level: RiskLevel
    reason: str
    customer_message: str
    draft_answer: str
    tool_calls: list[dict[str, Any]]
    node_runs: list[dict[str, Any]]
    human_feedback: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None

    @classmethod
    def from_model(cls, approval: AgentApproval) -> "AgentApprovalItem":
        return cls(
            id=str(approval.id),
            run_id=approval.run_id,
            ticket_id=approval.ticket_id,
            workspace_id=approval.workspace_id,
            request_id=approval.request_id,
            actor_hash=approval.actor_hash,
            status=approval.status,  # type: ignore[arg-type]
            category=approval.category,
            risk_level=approval.risk_level,  # type: ignore[arg-type]
            reason=approval.reason,
            customer_message=approval.customer_message,
            draft_answer=approval.draft_answer,
            tool_calls=list(approval.tool_calls),
            node_runs=list(approval.node_runs),
            human_feedback=approval.human_feedback,
            metadata=dict(approval.metadata_),
            created_at=approval.created_at,
            updated_at=approval.updated_at,
            decided_at=approval.decided_at,
        )


class AgentApprovalResponse(BaseModel):
    approval: AgentApprovalItem

    @classmethod
    def from_model(cls, approval: AgentApproval) -> "AgentApprovalResponse":
        return cls(approval=AgentApprovalItem.from_model(approval))


class AgentApprovalsResponse(BaseModel):
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
    approvals: list[AgentApprovalItem]

    @classmethod
    def from_result(
        cls,
        *,
        limit: int,
        offset: int,
        result: AgentApprovalListResult,
    ) -> "AgentApprovalsResponse":
        approvals = [
            AgentApprovalItem.from_model(approval)
            for approval in result.approvals
        ]
        return cls(
            total=result.total,
            count=len(approvals),
            limit=limit,
            offset=offset,
            approvals=approvals,
        )
