import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.security import require_api_key
from backend.app.core.logging import serialize_log_payload
from backend.app.core.request_id import get_request_id
from backend.app.db.repositories import ChatLogRepository, CreateChatLogInput
from backend.app.db.session import get_db_session
from backend.app.observability.metrics import metrics_registry
from backend.app.rag.openai_provider import OpenAIProviderError
from backend.app.rag.pipeline import ChatPipelineResponse, RagPipeline
from backend.app.schemas.chat import ChatLogsResponse, ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])
PROVIDER_LOGGER_NAME = "backend.provider"
PROVIDER_ERROR_STATUS_BY_CATEGORY = {
    "authentication": 502,
    "permission": 502,
    "not_found": 502,
    "invalid_request": 502,
    "rate_limit": 429,
    "timeout": 504,
    "network": 503,
    "server_error": 502,
    "conflict": 503,
}


async def get_rag_pipeline(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RagPipeline:
    return RagPipeline(session=session)


async def get_chat_log_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatLogRepository:
    return ChatLogRepository(session=session)


def normalize_workspace_id(workspace_id: str | None) -> str:
    if workspace_id is None:
        return "public"

    normalized = workspace_id.strip()
    return normalized or "public"


def build_chat_log_input(
    *,
    request_id: str,
    workspace_id: str,
    request: ChatRequest,
    response: ChatPipelineResponse,
) -> CreateChatLogInput:
    return CreateChatLogInput(
        request_id=request_id,
        workspace_id=workspace_id,
        question=request.question,
        answer=response.answer,
        sources=[source.model_dump(mode="json") for source in response.sources],
        retrieval=response.retrieval.model_dump(mode="json"),
        usage=response.usage.model_dump(mode="json"),
        refusal=(
            response.refusal.model_dump(mode="json")
            if response.refusal is not None
            else None
        ),
        citation_valid=response.citation_valid,
        latency_ms=response.usage.latency_ms,
    )


def map_provider_error_status(error: OpenAIProviderError) -> int:
    return PROVIDER_ERROR_STATUS_BY_CATEGORY.get(error.category, 502)


def build_provider_error_detail(
    *,
    error: OpenAIProviderError,
    request_id: str,
) -> dict[str, object]:
    return {
        "error": "provider_error",
        "provider": "openai",
        "category": error.category,
        "retryable": error.retryable,
        "request_id": request_id,
        "message": "The upstream OpenAI provider failed while processing the request.",
    }


def log_provider_error(
    *,
    error: OpenAIProviderError,
    request_id: str,
    workspace_id: str,
) -> None:
    logging.getLogger(PROVIDER_LOGGER_NAME).warning(
        serialize_log_payload(
            {
                "event": "provider_error",
                "provider": "openai",
                "operation": error.operation,
                "category": error.category,
                "retryable": error.retryable,
                "status_code": error.status_code,
                "request_id": request_id,
                "workspace_id": workspace_id,
            }
        )
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    http_request: Request,
    request: ChatRequest,
    _api_key: Annotated[str, Depends(require_api_key)],
    pipeline: Annotated[RagPipeline, Depends(get_rag_pipeline)],
    chat_log_repository: Annotated[
        ChatLogRepository,
        Depends(get_chat_log_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> ChatResponse:
    request_id = get_request_id(http_request)
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    try:
        response = await pipeline.answer_question(
            request.to_pipeline_request(
                workspace_id=normalized_workspace_id,
            )
        )
    except OpenAIProviderError as exc:
        metrics_registry.observe_provider_error(
            provider="openai",
            operation=exc.operation,
            category=exc.category,
        )
        log_provider_error(
            error=exc,
            request_id=request_id,
            workspace_id=normalized_workspace_id,
        )
        raise HTTPException(
            status_code=map_provider_error_status(exc),
            detail=build_provider_error_detail(error=exc, request_id=request_id),
        ) from exc

    metrics_registry.observe_rag_response(
        refusal_reason=response.refusal.reason if response.refusal else None,
        citation_valid=response.citation_valid,
    )
    await chat_log_repository.create_chat_log(
        build_chat_log_input(
            request_id=request_id,
            workspace_id=normalized_workspace_id,
            request=request,
            response=response,
        ),
        commit=True,
    )
    return ChatResponse.from_pipeline_response(
        response,
        request_id=request_id,
    )


@router.get("/chat/logs", response_model=ChatLogsResponse)
async def list_chat_logs(
    _api_key: Annotated[str, Depends(require_api_key)],
    chat_log_repository: Annotated[
        ChatLogRepository,
        Depends(get_chat_log_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ChatLogsResponse:
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    logs = await chat_log_repository.list_recent_chat_logs(
        workspace_id=normalized_workspace_id,
        limit=limit,
    )
    return ChatLogsResponse.from_logs(
        workspace_id=normalized_workspace_id,
        logs=logs,
    )
