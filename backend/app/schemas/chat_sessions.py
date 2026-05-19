from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.app.db.models import ChatSession
from backend.app.db.repositories import ChatSessionListResult


class CreateChatSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def title_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ChatSessionItem(BaseModel):
    id: str
    workspace_id: str
    title: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, chat_session: ChatSession) -> "ChatSessionItem":
        return cls(
            id=str(chat_session.id),
            workspace_id=chat_session.workspace_id,
            title=chat_session.title,
            metadata=dict(chat_session.metadata_),
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
        )


class ChatSessionResponse(BaseModel):
    workspace_id: str
    session: ChatSessionItem

    @classmethod
    def from_model(
        cls,
        *,
        workspace_id: str,
        chat_session: ChatSession,
    ) -> "ChatSessionResponse":
        return cls(
            workspace_id=workspace_id,
            session=ChatSessionItem.from_model(chat_session),
        )


class ChatSessionsResponse(BaseModel):
    workspace_id: str
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
    sessions: list[ChatSessionItem]

    @classmethod
    def from_result(
        cls,
        *,
        workspace_id: str,
        limit: int,
        offset: int,
        result: ChatSessionListResult,
    ) -> "ChatSessionsResponse":
        sessions = [
            ChatSessionItem.from_model(chat_session)
            for chat_session in result.sessions
        ]
        return cls(
            workspace_id=workspace_id,
            total=result.total,
            count=len(sessions),
            limit=limit,
            offset=offset,
            sessions=sessions,
        )
