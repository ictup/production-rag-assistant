import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from backend.app.api import routes_documents
from backend.app.core.config import Settings, get_settings
from backend.app.db.repositories import (
    DocumentChunkSummary,
    DocumentDetailResult,
    DocumentListResult,
    DocumentSummary,
    IngestDocumentResult,
)
from backend.app.main import create_app
from backend.app.rag.embeddings import FakeEmbeddingClient
from backend.app.rag.reindex_embeddings import ReindexEmbeddingsStats
from ingestion.models import Chunk, RawDocument

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class RecordingEmbeddingClient(FakeEmbeddingClient):
    def __init__(self) -> None:
        super().__init__(dimension=8, model_name="test-fake-embedding")
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts):
        self.calls.append(list(texts))
        return await super().embed_texts(texts)


class FakeReindexRunner:
    def __init__(self, stats: ReindexEmbeddingsStats | None = None) -> None:
        self.stats = stats or ReindexEmbeddingsStats(
            workspace_id="public",
            source_uri=None,
            model_name="not-used-dry-run",
            chunks_matched=0,
            chunks_embedded=0,
            chunks_updated=0,
            dry_run=True,
            elapsed_seconds=0.01,
        )
        self.calls: list[dict[str, object]] = []

    async def __call__(self, **kwargs: object) -> ReindexEmbeddingsStats:
        self.calls.append(dict(kwargs))
        return self.stats


class FakeDocumentRepository:
    def __init__(
        self,
        result: DocumentListResult | None = None,
        detail_result: DocumentDetailResult | None = None,
    ) -> None:
        self.result = result or DocumentListResult(total=0, documents=[])
        self.detail_result = detail_result
        self.delete_result = False
        self.existing_document_id: uuid.UUID | None = None
        self.list_calls: list[tuple[str, int, int]] = []
        self.detail_calls: list[tuple[uuid.UUID, str]] = []
        self.delete_calls: list[tuple[uuid.UUID, str, bool]] = []
        self.hash_calls: list[str] = []
        self.ingest_calls: list[dict[str, Any]] = []

    async def get_document_id_by_hash(self, content_hash: str) -> uuid.UUID | None:
        self.hash_calls.append(content_hash)
        return self.existing_document_id

    async def ingest_document(
        self,
        raw_document: RawDocument,
        chunks: list[Chunk],
        *,
        content_hash: str | None = None,
        chunk_embeddings: list[list[float]] | None = None,
        commit: bool = False,
    ) -> IngestDocumentResult:
        document_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        self.ingest_calls.append(
            {
                "raw_document": raw_document,
                "chunks": chunks,
                "content_hash": content_hash,
                "chunk_embeddings": chunk_embeddings,
                "commit": commit,
            }
        )
        return IngestDocumentResult(
            document_id=document_id,
            content_hash=content_hash or "unknown",
            inserted=True,
            chunks_inserted=len(chunks),
        )

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


def build_client(
    fake_repository: FakeDocumentRepository,
    embedding_client: RecordingEmbeddingClient | None = None,
    reindex_runner: FakeReindexRunner | None = None,
    fake_workspace_repository: FakeWorkspaceRepository | None = None,
    settings: Settings | None = None,
) -> TestClient:
    settings = settings or Settings(api_keys="dev-key")
    embedding_client = embedding_client or RecordingEmbeddingClient()
    reindex_runner = reindex_runner or FakeReindexRunner()
    fake_workspace_repository = fake_workspace_repository or FakeWorkspaceRepository()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_documents.get_document_repository] = (
        lambda: fake_repository
    )
    app.dependency_overrides[routes_documents.get_embedding_client] = (
        lambda: embedding_client
    )
    app.dependency_overrides[routes_documents.get_reindex_runner] = (
        lambda: reindex_runner
    )
    app.dependency_overrides[routes_documents.get_workspace_repository] = (
        lambda: fake_workspace_repository
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


def test_documents_route_rejects_forbidden_workspace_before_repository_call() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.get(
        "/documents",
        headers={
            "Authorization": "Bearer tenant-key",
            "X-Workspace-ID": "tenant-b",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
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


def test_create_document_route_ingests_markdown_for_workspace() -> None:
    fake_repository = FakeDocumentRepository()
    embedding_client = RecordingEmbeddingClient()
    client = build_client(fake_repository, embedding_client)

    response = client.post(
        "/documents",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        json={
            "source_uri": "uploads/flashattention.md",
            "markdown": """---
topic: "attention"
---

# FlashAttention

FlashAttention reduces HBM traffic.
""",
            "title": "Uploaded FlashAttention",
            "metadata": {"difficulty": "advanced"},
            "chunk_size_tokens": 40,
            "chunk_overlap_tokens": 5,
        },
    )

    assert response.status_code == 201
    assert len(fake_repository.hash_calls) == 1
    assert len(fake_repository.ingest_calls) == 1
    ingest_call = fake_repository.ingest_calls[0]
    raw_document = ingest_call["raw_document"]
    assert raw_document.workspace_id == "tenant-a"
    assert raw_document.title == "Uploaded FlashAttention"
    assert raw_document.source_uri == "uploads/flashattention.md"
    assert raw_document.metadata == {
        "topic": "attention",
        "difficulty": "advanced",
    }
    assert ingest_call["commit"] is True
    assert len(ingest_call["chunks"]) == 1
    assert len(ingest_call["chunk_embeddings"]) == 1
    assert embedding_client.calls != []
    body = response.json()
    assert body["workspace_id"] == "tenant-a"
    assert body["document_id"] == "33333333-3333-3333-3333-333333333333"
    assert body["inserted"] is True
    assert body["chunks_inserted"] == 1
    assert body["reason"] is None


def test_create_document_route_skips_duplicate_before_embedding() -> None:
    existing_document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    fake_repository = FakeDocumentRepository()
    fake_repository.existing_document_id = existing_document_id
    embedding_client = RecordingEmbeddingClient()
    client = build_client(fake_repository, embedding_client)

    response = client.post(
        "/documents",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "uploads/flashattention.md",
            "markdown": "# FlashAttention\n\nFlashAttention reduces HBM traffic.",
        },
    )

    assert response.status_code == 200
    assert len(fake_repository.hash_calls) == 1
    assert fake_repository.ingest_calls == []
    assert embedding_client.calls == []
    assert response.json() == {
        "workspace_id": "public",
        "document_id": str(existing_document_id),
        "content_hash": fake_repository.hash_calls[0],
        "inserted": False,
        "chunks_inserted": 0,
        "reason": "duplicate_content_hash",
    }


def test_create_document_route_rejects_invalid_front_matter() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/documents",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "uploads/bad.md",
            "markdown": "---\n- not\n- a\n- mapping\n---\nBody",
        },
    )

    assert response.status_code == 422
    assert fake_repository.hash_calls == []
    assert fake_repository.ingest_calls == []


def test_create_document_route_requires_api_key() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/documents",
        json={
            "source_uri": "uploads/flashattention.md",
            "markdown": "# FlashAttention\n\nFlashAttention reduces HBM traffic.",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_repository.ingest_calls == []


def test_create_document_route_rejects_missing_workspace_before_parsing() -> None:
    fake_repository = FakeDocumentRepository()
    embedding_client = RecordingEmbeddingClient()
    fake_workspace_repository = FakeWorkspaceRepository(workspace_ids={"public"})
    client = build_client(
        fake_repository,
        embedding_client,
        fake_workspace_repository=fake_workspace_repository,
    )

    response = client.post(
        "/documents",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-missing",
        },
        json={
            "source_uri": "uploads/flashattention.md",
            "markdown": "# FlashAttention\n\nFlashAttention reduces HBM traffic.",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_workspace_repository.get_calls == ["tenant-missing"]
    assert fake_repository.hash_calls == []
    assert fake_repository.ingest_calls == []
    assert embedding_client.calls == []


def test_create_document_route_rejects_archived_workspace_before_parsing() -> None:
    fake_repository = FakeDocumentRepository()
    embedding_client = RecordingEmbeddingClient()
    fake_workspace_repository = FakeWorkspaceRepository(
        archived_workspace_ids={"tenant-a"}
    )
    client = build_client(
        fake_repository,
        embedding_client,
        fake_workspace_repository=fake_workspace_repository,
    )

    response = client.post(
        "/documents",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        json={
            "source_uri": "uploads/flashattention.md",
            "markdown": "# FlashAttention\n\nFlashAttention reduces HBM traffic.",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "workspace archived"}
    assert fake_workspace_repository.get_calls == ["tenant-a"]
    assert fake_repository.hash_calls == []
    assert fake_repository.ingest_calls == []
    assert embedding_client.calls == []


def test_reindex_documents_route_runs_dry_run_by_default() -> None:
    reindex_runner = FakeReindexRunner(
        ReindexEmbeddingsStats(
            workspace_id="tenant-a",
            source_uri=None,
            model_name="not-used-dry-run",
            chunks_matched=3,
            chunks_embedded=0,
            chunks_updated=0,
            dry_run=True,
            elapsed_seconds=0.02,
        )
    )
    client = build_client(FakeDocumentRepository(), reindex_runner=reindex_runner)

    response = client.post(
        "/documents/reindex",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "  tenant-a  ",
        },
        json={},
    )

    assert response.status_code == 200
    assert reindex_runner.calls == [
        {
            "workspace_id": "tenant-a",
            "source_uri": None,
            "batch_size": 32,
            "limit": None,
            "dry_run": True,
        }
    ]
    assert response.json() == {
        "workspace_id": "tenant-a",
        "source_uri": None,
        "model": "not-used-dry-run",
        "chunks_matched": 3,
        "chunks_embedded": 0,
        "chunks_updated": 0,
        "dry_run": True,
        "elapsed_seconds": 0.02,
    }


def test_reindex_documents_route_passes_write_options() -> None:
    reindex_runner = FakeReindexRunner(
        ReindexEmbeddingsStats(
            workspace_id="tenant-a",
            source_uri="uploads/flashattention.md",
            model_name="test-embedding",
            chunks_matched=2,
            chunks_embedded=2,
            chunks_updated=2,
            dry_run=False,
            elapsed_seconds=1.25,
        )
    )
    client = build_client(FakeDocumentRepository(), reindex_runner=reindex_runner)

    response = client.post(
        "/documents/reindex",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        json={
            "source_uri": " uploads/flashattention.md ",
            "batch_size": 8,
            "limit": 10,
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    assert reindex_runner.calls == [
        {
            "workspace_id": "tenant-a",
            "source_uri": "uploads/flashattention.md",
            "batch_size": 8,
            "limit": 10,
            "dry_run": False,
        }
    ]
    assert response.json()["chunks_updated"] == 2
    assert response.json()["dry_run"] is False


def test_reindex_documents_route_requires_api_key() -> None:
    reindex_runner = FakeReindexRunner()
    client = build_client(FakeDocumentRepository(), reindex_runner=reindex_runner)

    response = client.post("/documents/reindex", json={})

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert reindex_runner.calls == []


def test_reindex_documents_route_rejects_invalid_options() -> None:
    reindex_runner = FakeReindexRunner()
    client = build_client(FakeDocumentRepository(), reindex_runner=reindex_runner)

    batch_response = client.post(
        "/documents/reindex",
        headers=AUTH_HEADERS,
        json={"batch_size": 0},
    )
    limit_response = client.post(
        "/documents/reindex",
        headers=AUTH_HEADERS,
        json={"limit": 0},
    )

    assert batch_response.status_code == 422
    assert limit_response.status_code == 422
    assert reindex_runner.calls == []


def test_reindex_documents_route_rejects_archived_workspace_before_runner() -> None:
    reindex_runner = FakeReindexRunner()
    fake_workspace_repository = FakeWorkspaceRepository(
        archived_workspace_ids={"tenant-a"}
    )
    client = build_client(
        FakeDocumentRepository(),
        reindex_runner=reindex_runner,
        fake_workspace_repository=fake_workspace_repository,
    )

    response = client.post(
        "/documents/reindex",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
        json={"dry_run": False},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "workspace archived"}
    assert fake_workspace_repository.get_calls == ["tenant-a"]
    assert reindex_runner.calls == []


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


def test_delete_document_route_rejects_archived_workspace_before_delete() -> None:
    document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    fake_repository = FakeDocumentRepository()
    fake_repository.delete_result = True
    fake_workspace_repository = FakeWorkspaceRepository(
        archived_workspace_ids={"tenant-a"}
    )
    client = build_client(
        fake_repository,
        fake_workspace_repository=fake_workspace_repository,
    )

    response = client.delete(
        f"/documents/{document_id}",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": "tenant-a",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "workspace archived"}
    assert fake_workspace_repository.get_calls == ["tenant-a"]
    assert fake_repository.delete_calls == []


def test_openapi_exposes_documents_route() -> None:
    fake_repository = FakeDocumentRepository()
    client = build_client(fake_repository)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/documents" in response.json()["paths"]
    assert "/documents/reindex" in response.json()["paths"]
    assert "/documents/{document_id}" in response.json()["paths"]
