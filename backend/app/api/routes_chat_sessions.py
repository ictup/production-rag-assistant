import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.security import ApiPrincipal, require_api_key, resolve_workspace_id
from backend.app.api.workspace_validation import (
    get_workspace_repository,
    require_active_workspace,
)
from backend.app.db.repositories import (
    ChatLogRepository,
    ChatSessionRepository,
    CreateChatSessionInput,
    WorkspaceRepository,
)
from backend.app.db.session import get_db_session
from backend.app.schemas.chat_sessions import (
    ChatSessionLogsResponse,
    ChatSessionResponse,
    ChatSessionsResponse,
    CreateChatSessionRequest,
)

router = APIRouter(tags=["chat"])


async def get_chat_session_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionRepository:
    return ChatSessionRepository(session=session)


async def get_chat_log_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatLogRepository:
    return ChatLogRepository(session=session)


async def get_chat_session_or_404(
    *,
    session_id: uuid.UUID,
    workspace_id: str,
    repository: ChatSessionRepository,
) -> None:
    chat_session = await repository.get_session(
        session_id=session_id,
        workspace_id=workspace_id,
    )
    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat session not found",
        )


@router.post(
    "/chat/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    request: CreateChatSessionRequest,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_repository: Annotated[
        WorkspaceRepository,
        Depends(get_workspace_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> ChatSessionResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    await require_active_workspace(
        workspace_id=normalized_workspace_id,
        repository=workspace_repository,
    )
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
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChatSessionsResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
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
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> ChatSessionResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
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


@router.get(
    "/chat/sessions/{session_id}/logs",
    response_model=ChatSessionLogsResponse,
)
async def list_chat_session_logs(
    session_id: uuid.UUID,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    chat_session_repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    chat_log_repository: Annotated[
        ChatLogRepository,
        Depends(get_chat_log_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChatSessionLogsResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    await get_chat_session_or_404(
        session_id=session_id,
        workspace_id=normalized_workspace_id,
        repository=chat_session_repository,
    )
    result = await chat_log_repository.list_chat_logs_by_session(
        session_id=session_id,
        workspace_id=normalized_workspace_id,
        limit=limit,
        offset=offset,
    )
    return ChatSessionLogsResponse.from_result(
        workspace_id=normalized_workspace_id,
        session_id=str(session_id),
        limit=limit,
        offset=offset,
        result=result,
    )
