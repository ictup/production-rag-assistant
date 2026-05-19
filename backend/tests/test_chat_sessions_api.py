import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.api import routes_chat_sessions
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import ChatSession
from backend.app.db.repositories import (
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


def make_chat_session_model() -> ChatSession:
    return ChatSession(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        workspace_id="tenant-a",
        title="GPU systems questions",
        metadata_={"topic": "systems"},
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )


def build_client(fake_repository: FakeChatSessionRepository) -> TestClient:
    settings = Settings(api_keys="dev-key")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_chat_sessions.get_chat_session_repository] = (
        lambda: fake_repository
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


def test_openapi_exposes_chat_session_routes() -> None:
    fake_repository = FakeChatSessionRepository()
    client = build_client(fake_repository)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/chat/sessions" in paths
    assert "/chat/sessions/{session_id}" in paths
