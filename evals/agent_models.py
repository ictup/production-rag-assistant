from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.agent.state import RiskLevel, TicketCategory
from backend.app.schemas.agent import (
    AgentRunStatus,
    CustomerTier,
    SupportTicketRequest,
    TicketPriority,
)

FINALIZED_AGENT_NODES = [
    "classify_ticket",
    "risk_check",
    "rag_search",
    "ticket_lookup",
    "draft_response",
]
APPROVAL_AGENT_NODES = [
    "classify_ticket",
    "risk_check",
]
FINALIZED_AGENT_TOOLS = [
    "classify_ticket_tool",
    "risk_check_tool",
    "rag_search_tool",
    "ticket_lookup_tool",
    "draft_response_tool",
]
APPROVAL_AGENT_TOOLS = [
    "classify_ticket_tool",
    "risk_check_tool",
]


class AgentEvalCase(BaseModel):
    id: str
    customer_message: str
    expected_category: TicketCategory
    expected_risk_level: RiskLevel
    expected_status: AgentRunStatus
    expected_approval_required: bool
    ticket_id: str | None = None
    priority: TicketPriority = "normal"
    workspace_id: str = "public"
    customer_tier: CustomerTier | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    expected_nodes: list[str] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)
    expected_answer_keywords: list[str] = Field(default_factory=list)
    expected_reason_keywords: list[str] = Field(default_factory=list)
    expected_citation_valid: bool | None = None

    @field_validator("id", "customer_message", "workspace_id")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator(
        "expected_nodes",
        "expected_tools",
        "expected_answer_keywords",
        "expected_reason_keywords",
    )
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @field_validator("ticket_id")
    @classmethod
    def normalize_optional_ticket_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("metadata", mode="before")
    @classmethod
    def metadata_must_be_object(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("metadata must be an object")
        return dict(value)

    @model_validator(mode="after")
    def validate_agent_eval_contract(self) -> "AgentEvalCase":
        if self.expected_status == "approval_required":
            if not self.expected_approval_required:
                raise ValueError(
                    "approval_required cases must expect approval_required=true"
                )
            if not self.expected_reason_keywords:
                raise ValueError(
                    "approval_required cases require expected_reason_keywords"
                )
            if self.expected_citation_valid is None:
                self.expected_citation_valid = None
        elif self.expected_status == "finalized":
            if self.expected_approval_required:
                raise ValueError(
                    "finalized cases must expect approval_required=false"
                )
            if not self.expected_answer_keywords:
                raise ValueError(
                    "finalized cases require expected_answer_keywords"
                )
            if self.expected_citation_valid is None:
                self.expected_citation_valid = True

        if not self.expected_nodes:
            self.expected_nodes = (
                APPROVAL_AGENT_NODES.copy()
                if self.expected_approval_required
                else FINALIZED_AGENT_NODES.copy()
            )
        if not self.expected_tools:
            self.expected_tools = (
                APPROVAL_AGENT_TOOLS.copy()
                if self.expected_approval_required
                else FINALIZED_AGENT_TOOLS.copy()
            )

        return self

    def to_request(self) -> SupportTicketRequest:
        return SupportTicketRequest(
            ticket_id=self.ticket_id or self.id,
            customer_message=self.customer_message,
            priority=self.priority,
            workspace_id=self.workspace_id,
            customer_tier=self.customer_tier,
            metadata=self.metadata,
        )


class AgentEvalDataset(BaseModel):
    name: str
    path: Path
    cases: list[AgentEvalCase]

    @property
    def total_cases(self) -> int:
        return len(self.cases)
