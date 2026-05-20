import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.api import routes_chat_sessions
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import ChatLog, ChatSession
from backend.app.db.repositories import (
    ChatLogListResult,
    ChatSessionListResult,
    CreateChatSessionInput,
)
from backend.app.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class FakeChatSessionRepository:
    def __init__(
        self,
        *,
        created_session: ChatSession | None = None,
        list_result: ChatSessionListResult | None = None,
        detail_session: ChatSession | None = None,
    ) -> None:
        self.created_session = created_session or make_chat_session_model()
        self.list_result = list_result or ChatSessionListResult(
            total=0,
            sessions=[],
        )
        self.detail_session = detail_session
        self.create_calls: list[tuple[CreateChatSessionInput, bool]] = []
        self.list_calls: list[tuple[str, int, int]] = []
        self.detail_calls: list[tuple[uuid.UUID, str]] = []

    async def create_session(
        self,
        session_input: CreateChatSessionInput,
        *,
        commit: bool = False,
    ) -> ChatSession:
        self.create_calls.append((session_input, commit))
        return self.created_session

    async def list_sessions(
        self,
        *,
        workspace_id: str = "public",
        limit: int = 20,
        offset: int = 0,
    ) -> ChatSessionListResult:
        self.list_calls.append((workspace_id, limit, offset))
        return self.list_result

    async def get_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: str = "public",
    ) -> ChatSession | None:
        self.detail_calls.append((session_id, workspace_id))
        return self.detail_session


class FakeChatLogRepository:
    def __init__(self, list_result: ChatLogListResult | None = None) -> None:
        self.list_result = list_result or ChatLogListResult(total=0, logs=[])
        self.list_calls: list[tuple[uuid.UUID, str, int, int]] = []

    async def list_chat_logs_by_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: str = "public",
        limit: int = 50,
        offset: int = 0,
    ) -> ChatLogListResult:
        self.list_calls.append((session_id, workspace_id, limit, offset))
        return self.list_result


class FakeWorkspaceRepository:
    def __init__(
        self,
        workspace_ids: set[str] | None = None,
        archived_workspace_ids: set[str] | None = None,
    ) -> None:
        self.workspace_ids = workspace_ids or {"public", "tenant-a"}
        self.archived_workspace_ids = archived_workspace_ids or set()
        self.get_calls: list[str] = []

    async def get_workspace(self, *, workspace_id: str):
        self.get_calls.append(workspace_id)
        if workspace_id in self.workspace_ids:
            archived_at = (
                datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
                if workspace_id in self.archived_workspace_ids
                else None
            )
            return SimpleNamespace(id=workspace_id, archived_at=archived_at)
        return None


def make_chat_session_model() -> ChatSession:
    return ChatSession(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        workspace_id="tenant-a",
        title="GPU systems questions",
        metadata_={"topic": "systems"},
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )


def make_chat_log_model() -> ChatLog:
    return ChatLog(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        request_id="request-1",
        workspace_id="tenant-a",
        session_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        question="What problem does FlashAttention solve?",
        answer="FlashAttention reduces memory traffic. [1]",
        sources=[{"source_id": "1", "title": "FlashAttention Notes"}],
        retrieval={"mode": "hybrid_rrf_rerank"},
        usage={"model": "fake-llm", "latency_ms": 12},
        refusal=None,
        citation_valid=True,
        latency_ms=12,
        created_at=datetime(2026, 5, 18, 8, 30, tzinfo=UTC),
    )


def build_client(
    fake_repository: FakeChatSessionRepository,
    fake_chat_log_repository: FakeChatLogRepository | None = None,
    fake_workspace_repository: FakeWorkspaceRepository | None = None,
    settings: Settings | None = None,
) -> TestClient:
    fake_chat_log_repository = fake_chat_log_repository or FakeChatLogRepository()
    fake_workspace_repository = fake_workspace_repository or FakeWorkspaceRepository()
    settings = settings or Settings(api_keys="dev-key")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_chat_sessions.get_chat_session_repository] = (
        lambda: fake_repository
    )
    app.dependency_overrides[routes_chat_sessions.get_chat_log_repository] = (
        lambda: fake_chat_log_repository
    )
    app.dependency_overrides[routes_chat_sessions.get_workspace_repository] = (
        lambda: fake_workspace_repository
    )
    return TestClient(app)


def test_create_chat_session_route_creates_session_for_workspace() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/chat/sessions",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        json={
            "title": " GPU systems questions ",
            "metadata": {"topic": "systems"},
        },
    )

    assert response.status_code == 201
    assert len(fake_repository.create_calls) == 1
    session_input, commit = fake_repository.create_calls[0]
    assert session_input.workspace_id == "tenant-a"
    assert session_input.title == "GPU systems questions"
    assert session_input.metadata == {"topic": "systems"}
    assert commit is True
    assert response.json()["workspace_id"] == "tenant-a"
    assert response.json()["session"]["id"] == "33333333-3333-3333-3333-333333333333"
    assert response.json()["session"]["metadata"] == {"topic": "systems"}


def test_create_chat_session_route_requires_api_key() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(fake_repository)

    response = client.post("/chat/sessions", json={})

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_repository.create_calls == []


def test_create_chat_session_route_rejects_missing_workspace_before_create() -> None:
    fake_repository = FakeChatSessionRepository()
    fake_workspace_repository = FakeWorkspaceRepository(workspace_ids={"public"})
    client = build_client(
        fake_repository,
        fake_workspace_repository=fake_workspace_repository,
    )

    response = client.post(
        "/chat/sessions",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-missing",
        },
        json={"title": "GPU systems questions"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_workspace_repository.get_calls == ["tenant-missing"]
    assert fake_repository.create_calls == []


def test_create_chat_session_route_rejects_archived_workspace_before_create() -> None:
    fake_repository = FakeChatSessionRepository()
    fake_workspace_repository = FakeWorkspaceRepository(
        archived_workspace_ids={"tenant-a"}
    )
    client = build_client(
        fake_repository,
        fake_workspace_repository=fake_workspace_repository,
    )

    response = client.post(
        "/chat/sessions",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        json={"title": "GPU systems questions"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "workspace archived"}
    assert fake_workspace_repository.get_calls == ["tenant-a"]
    assert fake_repository.create_calls == []


def test_list_chat_sessions_route_rejects_forbidden_workspace() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.get(
        "/chat/sessions",
        headers={
            "Authorization": "Bearer tenant-key",
            "X-Workspace-ID": "tenant-b",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_repository.list_calls == []


def test_list_chat_sessions_route_returns_paginated_sessions() -> None:
    chat_session = make_chat_session_model()
    fake_repository = FakeChatSessionRepository(
        list_result=ChatSessionListResult(total=7, sessions=[chat_session])
    )
    client = build_client(fake_repository)

    response = client.get(
        "/chat/sessions",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        params={"limit": 10, "offset": 5},
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [("tenant-a", 10, 5)]
    body = response.json()
    assert body["workspace_id"] == "tenant-a"
    assert body["total"] == 7
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["sessions"][0]["id"] == "33333333-3333-3333-3333-333333333333"
    assert body["sessions"][0]["title"] == "GPU systems questions"


def test_list_chat_sessions_route_defaults_workspace_and_pagination() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(fake_repository)

    response = client.get("/chat/sessions", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert fake_repository.list_calls == [("public", 20, 0)]
    assert response.json() == {
        "workspace_id": "public",
        "total": 0,
        "count": 0,
        "limit": 20,
        "offset": 0,
        "sessions": [],
    }


def test_list_chat_sessions_route_rejects_invalid_pagination() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(fake_repository)

    limit_response = client.get(
        "/chat/sessions",
        headers=AUTH_HEADERS,
        params={"limit": 0},
    )
    offset_response = client.get(
        "/chat/sessions",
        headers=AUTH_HEADERS,
        params={"offset": -1},
    )

    assert limit_response.status_code == 422
    assert offset_response.status_code == 422
    assert fake_repository.list_calls == []


def test_get_chat_session_route_returns_session_for_workspace() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    fake_repository = FakeChatSessionRepository(
        detail_session=make_chat_session_model()
    )
    client = build_client(fake_repository)

    response = client.get(
        f"/chat/sessions/{session_id}",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
    )

    assert response.status_code == 200
    assert fake_repository.detail_calls == [(session_id, "tenant-a")]
    assert response.json()["workspace_id"] == "tenant-a"
    assert response.json()["session"]["id"] == str(session_id)


def test_get_chat_session_route_returns_404_for_missing_session() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    fake_repository = FakeChatSessionRepository(detail_session=None)
    client = build_client(fake_repository)

    response = client.get(
        f"/chat/sessions/{session_id}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "chat session not found"}
    assert fake_repository.detail_calls == [(session_id, "public")]


def test_get_chat_session_route_rejects_invalid_uuid() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(fake_repository)

    response = client.get(
        "/chat/sessions/not-a-uuid",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422
    assert fake_repository.detail_calls == []


def test_list_chat_session_logs_route_returns_paginated_logs() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    fake_repository = FakeChatSessionRepository(
        detail_session=make_chat_session_model()
    )
    fake_chat_log_repository = FakeChatLogRepository(
        list_result=ChatLogListResult(total=3, logs=[make_chat_log_model()])
    )
    client = build_client(fake_repository, fake_chat_log_repository)

    response = client.get(
        f"/chat/sessions/{session_id}/logs",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        params={"limit": 2, "offset": 1},
    )

    assert response.status_code == 200
    assert fake_repository.detail_calls == [(session_id, "tenant-a")]
    assert fake_chat_log_repository.list_calls == [
        (session_id, "tenant-a", 2, 1)
    ]
    body = response.json()
    assert body["workspace_id"] == "tenant-a"
    assert body["session_id"] == str(session_id)
    assert body["total"] == 3
    assert body["count"] == 1
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert body["logs"][0]["id"] == "11111111-1111-1111-1111-111111111111"
    assert body["logs"][0]["session_id"] == str(session_id)
    assert body["logs"][0]["question"] == "What problem does FlashAttention solve?"


def test_list_chat_session_logs_route_returns_404_for_missing_session() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    fake_repository = FakeChatSessionRepository(detail_session=None)
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_repository, fake_chat_log_repository)

    response = client.get(
        f"/chat/sessions/{session_id}/logs",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "chat session not found"}
    assert fake_repository.detail_calls == [(session_id, "public")]
    assert fake_chat_log_repository.list_calls == []


def test_list_chat_session_logs_route_rejects_invalid_pagination() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    fake_repository = FakeChatSessionRepository(
        detail_session=make_chat_session_model()
    )
    fake_chat_log_repository = FakeChatLogRepository()
    client = build_client(fake_repository, fake_chat_log_repository)

    limit_response = client.get(
        f"/chat/sessions/{session_id}/logs",
        headers=AUTH_HEADERS,
        params={"limit": 0},
    )
    offset_response = client.get(
        f"/chat/sessions/{session_id}/logs",
        headers=AUTH_HEADERS,
        params={"offset": -1},
    )

    assert limit_response.status_code == 422
    assert offset_response.status_code == 422
    assert fake_repository.detail_calls == []
    assert fake_chat_log_repository.list_calls == []


def test_openapi_exposes_chat_session_routes() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(fake_repository)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/chat/sessions" in paths
    assert "/chat/sessions/{session_id}" in paths
    assert "/chat/sessions/{session_id}/logs" in paths
