import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.security import require_api_key
from backend.app.db.repositories import (
    ChatSessionRepository,
    CreateChatSessionInput,
)
from backend.app.db.session import get_db_session
from backend.app.schemas.chat_sessions import (
    ChatSessionResponse,
    ChatSessionsResponse,
    CreateChatSessionRequest,
)

router = APIRouter(tags=["chat"])


async def get_chat_session_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionRepository:
    return ChatSessionRepository(session=session)


def normalize_workspace_id(workspace_id: str | None) -> str:
    if workspace_id is None:
        return "public"

    normalized = workspace_id.strip()
    return normalized or "public"


@router.post(
    "/chat/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    request: CreateChatSessionRequest,
    _api_key: Annotated[str, Depends(require_api_key)],
    repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> ChatSessionResponse:
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    chat_session = await repository.create_session(
        CreateChatSessionInput(
            workspace_id=normalized_workspace_id,
            title=request.title,
            metadata=request.metadata,
        ),
        commit=True,
    )
    return ChatSessionResponse.from_model(
        workspace_id=normalized_workspace_id,
        chat_session=chat_session,
    )


@router.get("/chat/sessions", response_model=ChatSessionsResponse)
async def list_chat_sessions(
    _api_key: Annotated[str, Depends(require_api_key)],
    repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChatSessionsResponse:
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    result = await repository.list_sessions(
        workspace_id=normalized_workspace_id,
        limit=limit,
        offset=offset,
    )
    return ChatSessionsResponse.from_result(
        workspace_id=normalized_workspace_id,
        limit=limit,
        offset=offset,
        result=result,
    )


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: uuid.UUID,
    _api_key: Annotated[str, Depends(require_api_key)],
    repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> ChatSessionResponse:
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    chat_session = await repository.get_session(
        session_id=session_id,
        workspace_id=normalized_workspace_id,
    )
    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat session not found",
        )
    return ChatSessionResponse.from_model(
        workspace_id=normalized_workspace_id,
        chat_session=chat_session,
    )
