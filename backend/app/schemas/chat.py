import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.app.db.models import ChatLog
from backend.app.rag.citations import Source
from backend.app.rag.metadata_filters import normalize_metadata_filter
from backend.app.rag.pipeline import (
    ChatPipelineRequest,
    ChatPipelineResponse,
    RetrievalInfo,
    UsageInfo,
)
from backend.app.rag.query_rewriting import ConversationTurn
from backend.app.rag.refusal import RefusalInfo


class ChatRequest(BaseModel):
    question: str
    session_id: uuid.UUID | None = None
    metadata_filter: dict[str, Any] = Field(default_factory=dict)
    vector_top_k: int | None = Field(default=None, gt=0)
    sparse_top_k: int | None = Field(default=None, gt=0)
    fused_top_k: int | None = Field(default=None, gt=0)
    rerank_top_n: int | None = Field(default=None, gt=0)
    rerank: bool = True

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value

    @field_validator("metadata_filter", mode="before")
    @classmethod
    def metadata_filter_must_be_object(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("metadata_filter must be an object")
        return normalize_metadata_filter(value)

    def to_pipeline_request(
        self,
        *,
        workspace_id: str,
        chat_history: list[ConversationTurn] | None = None,
    ) -> ChatPipelineRequest:
        return ChatPipelineRequest(
            question=self.question,
            workspace_id=workspace_id,
            chat_history=list(chat_history or []),
            metadata_filter=self.metadata_filter,
            vector_top_k=self.vector_top_k,
            sparse_top_k=self.sparse_top_k,
            fused_top_k=self.fused_top_k,
            rerank_top_n=self.rerank_top_n,
            rerank=self.rerank,
        )


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    retrieval: RetrievalInfo
    usage: UsageInfo
    request_id: str
    session_id: str | None = None
    citation_valid: bool | None
    refusal: RefusalInfo | None = None

    @classmethod
    def from_pipeline_response(
        cls,
        response: ChatPipelineResponse,
        *,
        request_id: str,
        session_id: uuid.UUID | None = None,
    ) -> "ChatResponse":
        return cls(
            answer=response.answer,
            sources=response.sources,
            retrieval=response.retrieval,
            usage=response.usage,
            request_id=request_id,
            session_id=str(session_id) if session_id is not None else None,
            citation_valid=response.citation_valid,
            refusal=response.refusal,
        )


class ChatLogItem(BaseModel):
    id: str
    request_id: str
    workspace_id: str
    session_id: str | None
    question: str
    answer: str
    sources: list[dict[str, Any]]
    retrieval: dict[str, Any]
    usage: dict[str, Any]
    refusal: dict[str, Any] | None
    citation_valid: bool | None
    latency_ms: int
    created_at: datetime

    @classmethod
    def from_model(cls, chat_log: ChatLog) -> "ChatLogItem":
        return cls(
            id=str(chat_log.id),
            request_id=chat_log.request_id,
            workspace_id=chat_log.workspace_id,
            session_id=(
                str(chat_log.session_id) if chat_log.session_id is not None else None
            ),
            question=chat_log.question,
            answer=chat_log.answer,
            sources=list(chat_log.sources),
            retrieval=dict(chat_log.retrieval),
            usage=dict(chat_log.usage),
            refusal=dict(chat_log.refusal) if chat_log.refusal is not None else None,
            citation_valid=chat_log.citation_valid,
            latency_ms=chat_log.latency_ms,
            created_at=chat_log.created_at,
        )


class ChatLogsResponse(BaseModel):
    workspace_id: str
    count: int
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
    logs: list[ChatLogItem]

    @classmethod
    def from_logs(
        cls,
        *,
        workspace_id: str,
        limit: int,
        offset: int,
        logs: list[ChatLog],
    ) -> "ChatLogsResponse":
        return cls(
            workspace_id=workspace_id,
            count=len(logs),
            limit=limit,
            offset=offset,
            logs=[ChatLogItem.from_model(log) for log in logs],
        )
