import logging
import uuid
from collections.abc import AsyncIterator
from json import dumps as json_dumps
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.security import require_api_key
from backend.app.core.logging import serialize_log_payload
from backend.app.core.request_id import get_request_id
from backend.app.db.repositories import (
    ChatLogRepository,
    ChatSessionRepository,
    CreateChatLogInput,
)
from backend.app.db.session import get_db_session
from backend.app.observability.metrics import metrics_registry
from backend.app.rag.openai_provider import OpenAIProviderError
from backend.app.rag.pipeline import ChatPipelineResponse, RagPipeline
from backend.app.schemas.chat import ChatLogsResponse, ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])
PROVIDER_LOGGER_NAME = "backend.provider"
CHAT_STREAM_MEDIA_TYPE = "text/event-stream"
CHAT_STREAM_CHUNK_SIZE = 80
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


async def get_chat_session_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionRepository:
    return ChatSessionRepository(session=session)


def normalize_workspace_id(workspace_id: str | None) -> str:
    if workspace_id is None:
        return "public"

    normalized = workspace_id.strip()
    return normalized or "public"


def build_chat_log_input(
    *,
    request_id: str,
    workspace_id: str,
    session_id: uuid.UUID | None,
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
        session_id=session_id,
    )


async def resolve_chat_session_id(
    *,
    session_id: uuid.UUID | None,
    workspace_id: str,
    repository: ChatSessionRepository,
) -> uuid.UUID | None:
    if session_id is None:
        return None

    chat_session = await repository.get_session(
        session_id=session_id,
        workspace_id=workspace_id,
    )
    if chat_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat session not found",
        )
    return session_id


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


def observe_chat_provider_usage(response: ChatPipelineResponse) -> None:
    usage = response.usage
    if response.retrieval.mode != "question_guard":
        metrics_registry.observe_provider_latency(
            provider=usage.embedding_provider,
            operation="embedding",
            model=usage.embedding_model,
            latency_seconds=usage.embedding_latency_ms / 1000,
        )

    if response.refusal is None:
        metrics_registry.observe_provider_latency(
            provider=usage.generator_provider,
            operation="generation",
            model=usage.model,
            latency_seconds=usage.generation_latency_ms / 1000,
        )
        metrics_registry.observe_provider_tokens(
            provider=usage.generator_provider,
            model=usage.model,
            token_type="input",
            tokens=usage.input_tokens,
        )
        metrics_registry.observe_provider_tokens(
            provider=usage.generator_provider,
            model=usage.model,
            token_type="output",
            tokens=usage.output_tokens,
        )


async def run_chat_request(
    *,
    http_request: Request,
    request: ChatRequest,
    pipeline: RagPipeline,
    chat_log_repository: ChatLogRepository,
    chat_session_repository: ChatSessionRepository,
    workspace_id: str | None,
) -> tuple[str, uuid.UUID | None, ChatPipelineResponse]:
    request_id = get_request_id(http_request)
    normalized_workspace_id = normalize_workspace_id(workspace_id)
    session_id = await resolve_chat_session_id(
        session_id=request.session_id,
        workspace_id=normalized_workspace_id,
        repository=chat_session_repository,
    )
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
    observe_chat_provider_usage(response)
    await chat_log_repository.create_chat_log(
        build_chat_log_input(
            request_id=request_id,
            workspace_id=normalized_workspace_id,
            session_id=session_id,
            request=request,
            response=response,
        ),
        commit=True,
    )
    return request_id, session_id, response


def build_sse_event(*, event: str, data: dict[str, object]) -> str:
    payload = json_dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def split_answer_for_stream(answer: str) -> list[str]:
    if not answer:
        return []
    return [
        answer[index : index + CHAT_STREAM_CHUNK_SIZE]
        for index in range(0, len(answer), CHAT_STREAM_CHUNK_SIZE)
    ]


async def iter_chat_stream(
    *,
    response: ChatResponse,
) -> AsyncIterator[str]:
    yield build_sse_event(
        event="metadata",
        data={
            "request_id": response.request_id,
            "session_id": response.session_id,
            "citation_valid": response.citation_valid,
        },
    )
    for index, delta in enumerate(split_answer_for_stream(response.answer)):
        yield build_sse_event(
            event="answer_delta",
            data={
                "index": index,
                "delta": delta,
            },
        )
    yield build_sse_event(
        event="final",
        data=response.model_dump(mode="json"),
    )
    yield build_sse_event(
        event="done",
        data={
            "request_id": response.request_id,
        },
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
    chat_session_repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> ChatResponse:
    request_id, session_id, response = await run_chat_request(
        http_request=http_request,
        request=request,
        pipeline=pipeline,
        chat_log_repository=chat_log_repository,
        chat_session_repository=chat_session_repository,
        workspace_id=workspace_id,
    )
    return ChatResponse.from_pipeline_response(
        response,
        request_id=request_id,
        session_id=session_id,
    )


@router.post("/chat/stream")
async def chat_stream(
    http_request: Request,
    request: ChatRequest,
    _api_key: Annotated[str, Depends(require_api_key)],
    pipeline: Annotated[RagPipeline, Depends(get_rag_pipeline)],
    chat_log_repository: Annotated[
        ChatLogRepository,
        Depends(get_chat_log_repository),
    ],
    chat_session_repository: Annotated[
        ChatSessionRepository,
        Depends(get_chat_session_repository),
    ],
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
) -> StreamingResponse:
    request_id, session_id, pipeline_response = await run_chat_request(
        http_request=http_request,
        request=request,
        pipeline=pipeline,
        chat_log_repository=chat_log_repository,
        chat_session_repository=chat_session_repository,
        workspace_id=workspace_id,
    )
    response = ChatResponse.from_pipeline_response(
        pipeline_response,
        request_id=request_id,
        session_id=session_id,
    )
    return StreamingResponse(
        iter_chat_stream(response=response),
        media_type=CHAT_STREAM_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
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
