import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.api import routes_documents
from backend.app.core.config import Settings, get_settings
from backend.app.db.repositories import DocumentListResult, DocumentSummary
from backend.app.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class FakeDocumentRepository:
    def __init__(self, result: DocumentListResult | None = None) -> None:
        self.result = result or DocumentListResult(total=0, documents=[])
        self.list_calls: list[tuple[str, int, int]] = []

    async def list_documents(
        self,
        *,
        workspace_id: str = "public",
        limit: int = 20,
        offset: int = 0,
    ) -> DocumentListResult:
        self.list_calls.append((workspace_id, limit, offset))
        return self.result


def make_document_summary() -> DocumentSummary:
    return DocumentSummary(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        workspace_id="tenant-a",
        source_type="markdown",
        source_uri="data/raw/llm_systems/flashattention.md",
        title="FlashAttention Notes",
        author="Dao et al.",
        visibility="public",
        metadata={"topic": "attention"},
        chunk_count=3,
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )


def build_client(fake_repository: FakeDocumentRepository) -> TestClient:
    settings = Settings(api_keys="dev-key")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_documents.get_document_repository] = (
        lambda: fake_repository
    )
    return TestClient(app)


def test_documents_route_returns_paginated_documents_for_workspace() -> None:
    fake_repository = FakeDocumentRepository(
        DocumentListResult(total=7, documents=[make_document_summary()])
    )
    client = build_client(fake_repository)

    response = client.get(
        "/documents",
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
    assert body["documents"][0]["id"] == "11111111-1111-1111-1111-111111111111"
    assert body["documents"][0]["title"] == "FlashAttention Notes"
    assert body["documents"][0]["metadata"] == {"topic": "attention"}
    assert body["documents"][0]["chunk_count"] == 3


def test_documents_route_defaults_workspace_and_pagination() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.get("/documents", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert fake_repository.list_calls == [("public", 20, 0)]
    assert response.json() == {
        "workspace_id": "public",
        "total": 0,
        "count": 0,
        "limit": 20,
        "offset": 0,
        "documents": [],
    }


def test_documents_route_requires_api_key() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.get("/documents")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_repository.list_calls == []


def test_documents_route_rejects_invalid_pagination() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    limit_response = client.get(
        "/documents",
        headers=AUTH_HEADERS,
        params={"limit": 0},
    )
    offset_response = client.get(
        "/documents",
        headers=AUTH_HEADERS,
        params={"offset": -1},
    )

    assert limit_response.status_code == 422
    assert offset_response.status_code == 422
    assert fake_repository.list_calls == []


def test_openapi_exposes_documents_route() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/documents" in response.json()["paths"]
