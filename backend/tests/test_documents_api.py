import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.api import routes_documents
from backend.app.core.config import Settings, get_settings
from backend.app.db.repositories import (
    DocumentChunkSummary,
    DocumentDetailResult,
    DocumentListResult,
    DocumentSummary,
)
from backend.app.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class FakeDocumentRepository:
    def __init__(
        self,
        result: DocumentListResult | None = None,
        detail_result: DocumentDetailResult | None = None,
    ) -> None:
        self.result = result or DocumentListResult(total=0, documents=[])
        self.detail_result = detail_result
        self.delete_result = False
        self.list_calls: list[tuple[str, int, int]] = []
        self.detail_calls: list[tuple[uuid.UUID, str]] = []
        self.delete_calls: list[tuple[uuid.UUID, str, bool]] = []

    async def list_documents(
        self,
        *,
        workspace_id: str = "public",
        limit: int = 20,
        offset: int = 0,
    ) -> DocumentListResult:
        self.list_calls.append((workspace_id, limit, offset))
        return self.result

    async def get_document_detail(
        self,
        *,
        document_id: uuid.UUID,
        workspace_id: str = "public",
    ) -> DocumentDetailResult | None:
        self.detail_calls.append((document_id, workspace_id))
        return self.detail_result

    async def delete_document(
        self,
        *,
        document_id: uuid.UUID,
        workspace_id: str = "public",
        commit: bool = False,
    ) -> bool:
        self.delete_calls.append((document_id, workspace_id, commit))
        return self.delete_result


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


def make_chunk_summary() -> DocumentChunkSummary:
    return DocumentChunkSummary(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        document_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        workspace_id="tenant-a",
        chunk_index=0,
        text="FlashAttention reduces memory traffic.",
        token_count=5,
        section_title="FlashAttention",
        page_number=None,
        source_uri="data/raw/llm_systems/flashattention.md",
        metadata={"topic": "attention"},
        created_at=datetime(2026, 5, 18, 8, 5, tzinfo=UTC),
    )


def make_document_detail_result() -> DocumentDetailResult:
    return DocumentDetailResult(
        document=make_document_summary(),
        chunks=[make_chunk_summary()],
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


def test_document_detail_route_returns_document_and_chunks() -> None:
    document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    fake_repository = FakeDocumentRepository(
        detail_result=make_document_detail_result()
    )
    client = build_client(fake_repository)

    response = client.get(
        f"/documents/{document_id}",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
    )

    assert response.status_code == 200
    assert fake_repository.detail_calls == [(document_id, "tenant-a")]
    body = response.json()
    assert body["workspace_id"] == "tenant-a"
    assert body["document"]["id"] == str(document_id)
    assert body["document"]["chunk_count"] == 3
    assert body["chunks"][0]["id"] == "22222222-2222-2222-2222-222222222222"
    assert body["chunks"][0]["chunk_index"] == 0
    assert body["chunks"][0]["text"] == "FlashAttention reduces memory traffic."
    assert body["chunks"][0]["metadata"] == {"topic": "attention"}


def test_document_detail_route_returns_404_for_missing_document() -> None:
    document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    fake_repository = FakeDocumentRepository(detail_result=None)
    client = build_client(fake_repository)

    response = client.get(
        f"/documents/{document_id}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "document not found"}
    assert fake_repository.detail_calls == [(document_id, "public")]


def test_document_detail_route_rejects_invalid_uuid() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.get(
        "/documents/not-a-uuid",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422
    assert fake_repository.detail_calls == []


def test_document_detail_route_requires_api_key() -> None:
    fake_repository = FakeDocumentRepository(
        detail_result=make_document_detail_result()
    )
    client = build_client(fake_repository)

    response = client.get("/documents/11111111-1111-1111-1111-111111111111")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_repository.detail_calls == []


def test_delete_document_route_deletes_document_for_workspace() -> None:
    document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    fake_repository = FakeDocumentRepository()
    fake_repository.delete_result = True
    client = build_client(fake_repository)

    response = client.delete(
        f"/documents/{document_id}",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
    )

    assert response.status_code == 200
    assert fake_repository.delete_calls == [(document_id, "tenant-a", True)]
    assert response.json() == {
        "workspace_id": "tenant-a",
        "document_id": str(document_id),
        "deleted": True,
    }


def test_delete_document_route_returns_404_for_missing_document() -> None:
    document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.delete(
        f"/documents/{document_id}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "document not found"}
    assert fake_repository.delete_calls == [(document_id, "public", True)]


def test_delete_document_route_rejects_invalid_uuid() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.delete(
        "/documents/not-a-uuid",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422
    assert fake_repository.delete_calls == []


def test_delete_document_route_requires_api_key() -> None:
    fake_repository = FakeDocumentRepository()
    fake_repository.delete_result = True
    client = build_client(fake_repository)

    response = client.delete("/documents/11111111-1111-1111-1111-111111111111")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_repository.delete_calls == []


def test_openapi_exposes_documents_route() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/documents" in response.json()["paths"]
    assert "/documents/{document_id}" in response.json()["paths"]
