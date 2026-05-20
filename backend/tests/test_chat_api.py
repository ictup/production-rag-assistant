import json
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_chat
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import ChatLog, ChatSession
from backend.app.db.repositories import CreateChatLogInput
from backend.app.main import create_app
from backend.app.observability.metrics import metrics_registry
from backend.app.rag.citations import Source
from backend.app.rag.openai_provider import OpenAIErrorInfo, OpenAIProviderError
from backend.app.rag.pipeline import (
    ChatPipelineRequest,
    ChatPipelineResponse,
    ChatPipelineStreamEvent,
    RetrievalInfo,
    UsageInfo,
)
from backend.app.rag.refusal import REFUSAL_ANSWER, RefusalInfo

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class FakePipeline:
    def __init__(
        self,
        *,
        citation_valid: bool | None = True,
        refusal: RefusalInfo | None = None,
        error: Exception | None = None,
        usage: UsageInfo | None = None,
    ) -> None:
        self.requests: list[ChatPipelineRequest] = []
        self.citation_valid = citation_valid
        self.refusal = refusal
        self.error = error
        self.usage = usage

    async def answer_question(
        self,
        request: ChatPipelineRequest,
    ) -> ChatPipelineResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        is_refusal = self.refusal is not None
        answer = (
            REFUSAL_ANSWER
            if is_refusal
            else "FlashAttention reduces memory traffic. [1]"
        )
        return ChatPipelineResponse(
            answer=answer,
            sources=[] if is_refusal else [make_source()],
            retrieval=RetrievalInfo(
                mode="hybrid_rrf_rerank",
                vector_top_k=request.vector_top_k or 20,
                sparse_top_k=request.sparse_top_k or 20,
                fused_count=1,
                used_count=1,
                top_score=0.42,
                metadata_filter=request.metadata_filter,
            ),
            usage=self.usage
            or UsageInfo(
                model="test-fake-llm",
                embedding_model="test-fake-embedding",
                latency_ms=12,
                generator_provider="fake",
                embedding_provider="fake",
                embedding_latency_ms=7,
                generation_latency_ms=5,
                embedding_input_tokens=4,
                embedding_total_tokens=4,
                input_tokens=10,
                output_tokens=5,
            ),
            citation_valid=self.citation_valid,
            refusal=self.refusal,
        )

    async def stream_answer(self, request: ChatPipelineRequest):
        response = await self.answer_question(request)
        yield ChatPipelineStreamEvent(
            event_type="delta",
            delta=response.answer,
        )
        yield ChatPipelineStreamEvent(
            event_type="completed",
            response=response,
        )


class FakeChatLogRepository:
    def __init__(
        self,
        recent_logs: list[ChatLog] | None = None,
        session_logs: list[ChatLog] | None = None,
    ) -> None:
        self.inputs: list[CreateChatLogInput] = []
        self.commit_flags: list[bool] = []
        self.recent_logs = recent_logs or []
        self.session_logs = session_logs or []
        self.list_calls: list[dict[str, object]] = []
        self.session_log_calls: list[tuple[uuid.UUID, str, int]] = []

    async def create_chat_log(
        self,
        log_input: CreateChatLogInput,
        *,
        commit: bool = False,
    ) -> None:
        self.inputs.append(log_input)
        self.commit_flags.append(commit)

    async def list_recent_chat_logs(
        self,
        *,
        workspace_id: str = "public",
        limit: int = 10,
        offset: int = 0,
        session_id: uuid.UUID | None = None,
        request_id: str | None = None,
        refusal_only: bool = False,
        citation_valid: bool | None = None,
    ) -> list[ChatLog]:
        self.list_calls.append(
            {
                "workspace_id": workspace_id,
                "limit": limit,
                "offset": offset,
                "session_id": session_id,
                "request_id": request_id,
                "refusal_only": refusal_only,
                "citation_valid": citation_valid,
            }
        )
        return self.recent_logs

    async def list_recent_chat_logs_by_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: str = "public",
        limit: int = 4,
    ) -> list[ChatLog]:
        self.session_log_calls.append((session_id, workspace_id, limit))
        return self.session_logs


class FakeChatSessionRepository:
    def __init__(self, sessions: list[ChatSession] | None = None) -> None:
        self.sessions = {
            (chat_session.id, chat_session.workspace_id): chat_session
            for chat_session in sessions or []
        }
        self.get_calls: list[tuple[uuid.UUID, str]] = []

    async def get_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: str = "public",
    ) -> ChatSession | None:
        self.get_calls.append((session_id, workspace_id))
        return self.sessions.get((session_id, workspace_id))


class FakeWorkspaceRepository:
    def __init__(self, workspace_ids: set[str] | None = None) -> None:
        self.workspace_ids = workspace_ids or {"public", "tenant-a"}
        self.get_calls: list[str] = []

    async def get_workspace(self, *, workspace_id: str):
        self.get_calls.append(workspace_id)
        if workspace_id in self.workspace_ids:
            return object()
        return None


def make_source() -> Source:
    return Source(
        source_id="1",
        title="FlashAttention Notes",
        section="FlashAttention",
        source_uri="llm_systems/flashattention.md",
        chunk_id="chunk-1",
        score=0.42,
    )


def make_chat_log_model(
    *,
    session_id: uuid.UUID | None = None,
    question: str = "What problem does FlashAttention solve?",
    answer: str = "FlashAttention reduces memory traffic. [1]",
) -> ChatLog:
    return ChatLog(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        request_id="request-1",
        workspace_id="tenant-a",
        session_id=session_id,
        question=question,
        answer=answer,
        sources=[{"source_id": "1", "title": "FlashAttention Notes"}],
        retrieval={"mode": "hybrid_rrf_rerank"},
        usage={"model": "fake-llm", "latency_ms": 12},
        refusal=None,
        citation_valid=True,
        latency_ms=12,
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
    )


def make_chat_session_model() -> ChatSession:
    return ChatSession(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        workspace_id="tenant-a",
        title="GPU systems questions",
        metadata_={"topic": "systems"},
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )


def make_provider_error(
    *,
    category: str = "rate_limit",
    retryable: bool = True,
    status_code: int | None = 429,
) -> OpenAIProviderError:
    return OpenAIProviderError(
        OpenAIErrorInfo(
            operation="OpenAI response request",
            category=category,
            message=f"OpenAI response request failed ({category})",
            retryable=retryable,
            status_code=status_code,
        )
    )


def build_client(
    fake_pipeline: FakePipeline,
    fake_chat_log_repository: FakeChatLogRepository | None = None,
    fake_chat_session_repository: FakeChatSessionRepository | None = None,
    fake_workspace_repository: FakeWorkspaceRepository | None = None,
    settings: Settings | None = None,
) -> TestClient:
    fake_chat_log_repository = fake_chat_log_repository or FakeChatLogRepository()
    fake_chat_session_repository = (
        fake_chat_session_repository or FakeChatSessionRepository()
    )
    fake_workspace_repository = fake_workspace_repository or FakeWorkspaceRepository()
    settings = settings or Settings(api_keys="dev-key")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_chat.get_rag_pipeline] = lambda: fake_pipeline
    app.dependency_overrides[routes_chat.get_chat_log_repository] = (
        lambda: fake_chat_log_repository
    )
    app.dependency_overrides[routes_chat.get_chat_session_repository] = (
        lambda: fake_chat_session_repository
    )
    app.dependency_overrides[routes_chat.get_workspace_repository] = (
        lambda: fake_workspace_repository
    )
    return TestClient(app)


def parse_sse_events(stream_text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in stream_text.strip().split("\n\n"):
        event_name: str | None = None
        event_data: dict | None = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            if line.startswith("data: "):
                event_data = json.loads(line.removeprefix("data: "))
        if event_name is not None and event_data is not None:
            events.append((event_name, event_data))
    return events


def test_chat_route_returns_answer_sources_and_metadata() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.post(
        "/chat",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        json={
            "question": "  What problem does FlashAttention solve?  ",
            "vector_top_k": 3,
            "sparse_top_k": 4,
            "fused_top_k": 5,
            "rerank_top_n": 2,
            "rerank": False,
            "metadata_filter": {" topic ": "attention"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "FlashAttention reduces memory traffic. [1]"
    assert body["sources"][0]["source_id"] == "1"
    assert body["retrieval"]["mode"] == "hybrid_rrf_rerank"
    assert body["usage"]["model"] == "test-fake-llm"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["session_id"] is None
    assert body["citation_valid"] is True

    assert len(fake_pipeline.requests) == 1
    pipeline_request = fake_pipeline.requests[0]
    assert pipeline_request.question == "What problem does FlashAttention solve?"
    assert pipeline_request.workspace_id == "tenant-a"
    assert pipeline_request.vector_top_k == 3
    assert pipeline_request.sparse_top_k == 4
    assert pipeline_request.fused_top_k == 5
    assert pipeline_request.rerank_top_n == 2
    assert pipeline_request.rerank is False
    assert pipeline_request.metadata_filter == {"topic": "attention"}
    assert body["retrieval"]["metadata_filter"] == {"topic": "attention"}

    assert len(fake_chat_log_repository.inputs) == 1
    assert fake_chat_log_repository.commit_flags == [True]
    chat_log_input = fake_chat_log_repository.inputs[0]
    assert chat_log_input.request_id == body["request_id"]
    assert chat_log_input.workspace_id == "tenant-a"
    assert chat_log_input.session_id is None
    assert chat_log_input.question == "What problem does FlashAttention solve?"
    assert chat_log_input.answer == body["answer"]
    assert chat_log_input.sources == body["sources"]
    assert chat_log_input.retrieval == body["retrieval"]
    assert chat_log_input.usage == body["usage"]
    assert chat_log_input.refusal is None
    assert chat_log_input.citation_valid is True
    assert chat_log_input.latency_ms == body["usage"]["latency_ms"]


def test_chat_route_attaches_log_to_existing_session() -> None:
    chat_session = make_chat_session_model()
    fake_pipeline = FakePipeline()
    history_log = make_chat_log_model(
        session_id=chat_session.id,
        question="What is FlashAttention?",
        answer="FlashAttention is IO-aware attention.",
    )
    fake_chat_log_repository = FakeChatLogRepository(session_logs=[history_log])
    fake_chat_session_repository = FakeChatSessionRepository(sessions=[chat_session])
    client = build_client(
        fake_pipeline,
        fake_chat_log_repository,
        fake_chat_session_repository,
    )

    response = client.post(
        "/chat",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        json={
            "question": "What problem does FlashAttention solve?",
            "session_id": str(chat_session.id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == str(chat_session.id)
    assert fake_chat_session_repository.get_calls == [(chat_session.id, "tenant-a")]
    assert fake_chat_log_repository.session_log_calls == [
        (chat_session.id, "tenant-a", 4)
    ]
    assert len(fake_pipeline.requests) == 1
    assert (
        fake_pipeline.requests[0].chat_history[0].question
        == "What is FlashAttention?"
    )
    assert fake_pipeline.requests[0].chat_history[0].answer == (
        "FlashAttention is IO-aware attention."
    )
    assert len(fake_chat_log_repository.inputs) == 1
    assert fake_chat_log_repository.inputs[0].session_id == chat_session.id


def test_chat_route_skips_session_history_when_limit_is_zero() -> None:
    chat_session = make_chat_session_model()
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository(
        session_logs=[
            make_chat_log_model(
                session_id=chat_session.id,
                question="What is FlashAttention?",
                answer="FlashAttention is IO-aware attention.",
            )
        ]
    )
    fake_chat_session_repository = FakeChatSessionRepository(sessions=[chat_session])
    client = build_client(
        fake_pipeline,
        fake_chat_log_repository,
        fake_chat_session_repository,
        settings=Settings(api_keys="dev-key", query_context_history_limit=0),
    )

    response = client.post(
        "/chat",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        json={
            "question": "What problem does it solve?",
            "session_id": str(chat_session.id),
        },
    )

    assert response.status_code == 200
    assert fake_chat_log_repository.session_log_calls == []
    assert fake_pipeline.requests[0].chat_history == []


def test_chat_route_rejects_missing_session_before_pipeline_call() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    fake_chat_session_repository = FakeChatSessionRepository()
    client = build_client(
        fake_pipeline,
        fake_chat_log_repository,
        fake_chat_session_repository,
    )

    response = client.post(
        "/chat",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        json={
            "question": "What problem does FlashAttention solve?",
            "session_id": str(session_id),
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "chat session not found"}
    assert fake_chat_session_repository.get_calls == [(session_id, "tenant-a")]
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_route_rejects_missing_workspace_before_pipeline_call() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    fake_workspace_repository = FakeWorkspaceRepository(workspace_ids={"public"})
    client = build_client(
        fake_pipeline,
        fake_chat_log_repository,
        fake_workspace_repository=fake_workspace_repository,
    )

    response = client.post(
        "/chat",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-missing",
        },
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_workspace_repository.get_calls == ["tenant-missing"]
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_stream_route_returns_sse_events_and_logs_chat() -> None:
    chat_session = make_chat_session_model()
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    fake_chat_session_repository = FakeChatSessionRepository(sessions=[chat_session])
    client = build_client(
        fake_pipeline,
        fake_chat_log_repository,
        fake_chat_session_repository,
    )

    response = client.post(
        "/chat/stream",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        json={
            "question": "What problem does FlashAttention solve?",
            "session_id": str(chat_session.id),
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse_events(response.text)
    assert [event_name for event_name, _ in events] == [
        "metadata",
        "answer_delta",
        "final",
        "done",
    ]
    metadata = events[0][1]
    final = events[2][1]
    assert metadata["request_id"] == response.headers["X-Request-ID"]
    assert metadata["session_id"] == str(chat_session.id)
    assert final["session_id"] == str(chat_session.id)
    assert final["request_id"] == response.headers["X-Request-ID"]
    assert final["answer"] == events[1][1]["delta"]
    assert fake_chat_log_repository.session_log_calls == [
        (chat_session.id, "tenant-a", 4)
    ]
    assert fake_pipeline.requests[0].chat_history == []
    assert fake_chat_log_repository.commit_flags == [True]
    assert fake_chat_log_repository.inputs[0].session_id == chat_session.id


def test_chat_stream_route_rejects_missing_session_before_pipeline_call() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    fake_chat_session_repository = FakeChatSessionRepository()
    client = build_client(
        fake_pipeline,
        fake_chat_log_repository,
        fake_chat_session_repository,
    )

    response = client.post(
        "/chat/stream",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        json={
            "question": "What problem does FlashAttention solve?",
            "session_id": str(session_id),
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "chat session not found"}
    assert fake_chat_session_repository.get_calls == [(session_id, "tenant-a")]
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_route_defaults_workspace_to_public() -> None:
    fake_pipeline = FakePipeline()
    client = build_client(fake_pipeline)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 200
    assert fake_pipeline.requests[0].workspace_id == "public"


def test_chat_route_uses_client_request_id() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.post(
        "/chat",
        headers={
            **AUTH_HEADERS,
            "X-Request-ID": "  client-request-123  ",
        },
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 200
    assert response.json()["request_id"] == "client-request-123"
    assert response.headers["X-Request-ID"] == "client-request-123"
    assert fake_chat_log_repository.inputs[0].request_id == "client-request-123"


def test_chat_route_rejects_blank_question() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={"question": "   "},
    )

    assert response.status_code == 422
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_route_rejects_invalid_metadata_filter() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={
            "question": "What is FlashAttention?",
            "metadata_filter": {"  ": "attention"},
        },
    )

    assert response.status_code == 422
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_route_rejects_missing_api_key() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.post(
        "/chat",
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_route_rejects_invalid_api_key() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.post(
        "/chat",
        headers={"Authorization": "Bearer wrong-key"},
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid api key"}
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_route_rejects_forbidden_workspace_before_pipeline_call() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(
        fake_pipeline,
        fake_chat_log_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.post(
        "/chat",
        headers={
            "Authorization": "Bearer tenant-key",
            "X-Workspace-ID": "tenant-b",
        },
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_pipeline.requests == []
    assert fake_chat_log_repository.inputs == []


def test_chat_route_records_refusal_metric() -> None:
    metrics_registry.reset()
    fake_pipeline = FakePipeline(
        citation_valid=None,
        refusal=RefusalInfo(
            reason="no_retrieved_chunks",
            top_score=None,
            threshold=0.01,
        ),
    )
    client = build_client(fake_pipeline)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={"question": "What is an unrelated topic?"},
    )

    assert response.status_code == 200
    assert (
        'rag_refusals_total{reason="no_retrieved_chunks"} 1'
        in metrics_registry.render_prometheus()
    )


def test_chat_route_records_invalid_citation_metric() -> None:
    metrics_registry.reset()
    fake_pipeline = FakePipeline(citation_valid=False)
    client = build_client(fake_pipeline)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 200
    assert "rag_citation_invalid_total 1" in metrics_registry.render_prometheus()


def test_chat_route_records_provider_usage_metrics() -> None:
    metrics_registry.reset()
    fake_pipeline = FakePipeline()
    client = build_client(fake_pipeline)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 200
    output = metrics_registry.render_prometheus()
    assert (
        'rag_provider_latency_seconds_count{provider="fake",'
        'operation="embedding",model="test-fake-embedding"} 1'
    ) in output
    assert (
        'rag_provider_latency_seconds_count{provider="fake",'
        'operation="generation",model="test-fake-llm"} 1'
    ) in output
    assert (
        'rag_provider_tokens_total{provider="fake",model="test-fake-llm",'
        'token_type="input"} 10'
    ) in output
    assert (
        'rag_provider_tokens_total{provider="fake",model="test-fake-llm",'
        'token_type="output"} 5'
    ) in output
    assert (
        'rag_provider_tokens_total{provider="fake",model="test-fake-embedding",'
        'token_type="input"} 4'
    ) in output


def test_chat_route_records_provider_cost_metric() -> None:
    metrics_registry.reset()
    fake_pipeline = FakePipeline(
        usage=UsageInfo(
            model="test-fake-llm",
            embedding_model="test-fake-embedding",
            latency_ms=12,
            generator_provider="fake",
            embedding_provider="fake",
            embedding_latency_ms=7,
            generation_latency_ms=5,
            embedding_input_tokens=20,
            embedding_total_tokens=20,
            embedding_cost_usd=0.000002,
            embedding_cost_estimated=True,
            input_tokens=10,
            output_tokens=5,
            input_cost_usd=0.000005,
            output_cost_usd=0.000005,
            total_cost_usd=0.000012,
            cost_estimated=True,
        )
    )
    client = build_client(fake_pipeline)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == 200
    assert (
        'rag_provider_cost_usd_total{provider="fake",model="test-fake-llm"} 1e-05'
        in metrics_registry.render_prometheus()
    )
    assert (
        'rag_provider_cost_usd_total{provider="fake",'
        'model="test-fake-embedding"} 2e-06'
        in metrics_registry.render_prometheus()
    )


@pytest.mark.parametrize(
    ("category", "retryable", "status_code", "expected_status_code"),
    [
        ("rate_limit", True, 429, 429),
        ("timeout", True, None, 504),
        ("network", True, None, 503),
        ("authentication", False, 401, 502),
        ("invalid_request", False, 400, 502),
    ],
)
def test_chat_route_maps_provider_errors_to_api_response_and_metrics(
    category: str,
    retryable: bool,
    status_code: int | None,
    expected_status_code: int,
) -> None:
    metrics_registry.reset()
    provider_error = make_provider_error(
        category=category,
        retryable=retryable,
        status_code=status_code,
    )
    fake_pipeline = FakePipeline(error=provider_error)
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.post(
        "/chat",
        headers=AUTH_HEADERS,
        json={"question": "What is FlashAttention?"},
    )

    assert response.status_code == expected_status_code
    body = response.json()
    assert body["detail"]["error"] == "provider_error"
    assert body["detail"]["provider"] == "openai"
    assert body["detail"]["category"] == category
    assert body["detail"]["retryable"] is retryable
    assert body["detail"]["request_id"] == response.headers["X-Request-ID"]
    assert fake_chat_log_repository.inputs == []
    assert (
        'rag_provider_errors_total{provider="openai",'
        'operation="OpenAI response request",'
        f'category="{category}"}} 1'
    ) in metrics_registry.render_prometheus()


def test_chat_route_logs_provider_error(caplog) -> None:
    metrics_registry.reset()
    fake_pipeline = FakePipeline(
        error=make_provider_error(category="rate_limit", retryable=True)
    )
    client = build_client(fake_pipeline)

    with caplog.at_level("WARNING", logger=routes_chat.PROVIDER_LOGGER_NAME):
        response = client.post(
            "/chat",
            headers=AUTH_HEADERS,
            json={"question": "What is FlashAttention?"},
        )

    assert response.status_code == 429
    assert '"event":"provider_error"' in caplog.text
    assert '"category":"rate_limit"' in caplog.text


def test_openapi_exposes_chat_route() -> None:
    fake_pipeline = FakePipeline()
    client = build_client(fake_pipeline)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/chat" in response.json()["paths"]
    assert "/chat/stream" in response.json()["paths"]


def test_chat_logs_route_returns_recent_logs_for_workspace() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository(
        recent_logs=[make_chat_log_model()]
    )
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.get(
        "/chat/logs",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        params={"limit": 3},
    )

    assert response.status_code == 200
    assert fake_chat_log_repository.list_calls == [
        {
            "workspace_id": "tenant-a",
            "limit": 3,
            "offset": 0,
            "session_id": None,
            "request_id": None,
            "refusal_only": False,
            "citation_valid": None,
        }
    ]
    body = response.json()
    assert body["workspace_id"] == "tenant-a"
    assert body["count"] == 1
    assert body["limit"] == 3
    assert body["offset"] == 0
    assert body["logs"][0]["id"] == "11111111-1111-1111-1111-111111111111"
    assert body["logs"][0]["request_id"] == "request-1"
    assert body["logs"][0]["session_id"] is None
    assert body["logs"][0]["question"] == "What problem does FlashAttention solve?"
    assert body["logs"][0]["citation_valid"] is True
    assert body["logs"][0]["sources"][0]["source_id"] == "1"


def test_chat_logs_route_defaults_workspace_to_public() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.get("/chat/logs", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert fake_chat_log_repository.list_calls == [
        {
            "workspace_id": "public",
            "limit": 10,
            "offset": 0,
            "session_id": None,
            "request_id": None,
            "refusal_only": False,
            "citation_valid": None,
        }
    ]
    assert response.json() == {
        "workspace_id": "public",
        "count": 0,
        "limit": 10,
        "offset": 0,
        "logs": [],
    }


def test_chat_logs_route_requires_api_key() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.get("/chat/logs")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_chat_log_repository.list_calls == []


def test_chat_logs_route_rejects_invalid_limit() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)

    response = client.get(
        "/chat/logs",
        headers=AUTH_HEADERS,
        params={"limit": 0},
    )

    assert response.status_code == 422
    assert fake_chat_log_repository.list_calls == []


def test_chat_logs_route_forwards_audit_filters() -> None:
    fake_pipeline = FakePipeline()
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_pipeline, fake_chat_log_repository)
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")

    response = client.get(
        "/chat/logs",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        params={
            "limit": 5,
            "offset": 10,
            "session_id": str(session_id),
            "request_id": "request-1",
            "refusal_only": "true",
            "citation_valid": "false",
        },
    )

    assert response.status_code == 200
    assert fake_chat_log_repository.list_calls == [
        {
            "workspace_id": "tenant-a",
            "limit": 5,
            "offset": 10,
            "session_id": session_id,
            "request_id": "request-1",
            "refusal_only": True,
            "citation_valid": False,
        }
    ]
    assert response.json()["offset"] == 10
