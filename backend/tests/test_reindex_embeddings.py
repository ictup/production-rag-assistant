import uuid
from collections.abc import Sequence
from typing import Any

import pytest

from backend.app.db.models import EMBEDDING_DIMENSION
from backend.app.rag.reindex_embeddings import (
    ChunkEmbeddingTarget,
    ReindexEmbeddingsStats,
    build_count_reindex_chunks_statement,
    build_fetch_reindex_batch_statement,
    fetch_reindex_batch,
    format_reindex_stats,
    reindex_embeddings,
    update_chunk_embeddings,
)


class FakeRow:
    def __init__(self, **mapping: Any) -> None:
        self._mapping = mapping


class FakeExecuteResult:
    def __init__(self, rows: list[FakeRow]) -> None:
        self.rows = rows

    def all(self) -> list[FakeRow]:
        return self.rows


class FakeSession:
    def __init__(
        self,
        *,
        count: int = 0,
        fetch_batches: list[list[FakeRow]] | None = None,
    ) -> None:
        self.count = count
        self.fetch_batches = fetch_batches or []
        self.scalar_statements: list[Any] = []
        self.select_statements: list[Any] = []
        self.update_statements: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, statement: Any) -> int:
        self.scalar_statements.append(statement)
        return self.count

    async def execute(self, statement: Any) -> FakeExecuteResult:
        compiled = str(statement)
        if compiled.lstrip().upper().startswith("SELECT"):
            self.select_statements.append(statement)
            rows = self.fetch_batches.pop(0) if self.fetch_batches else []
            return FakeExecuteResult(rows)

        self.update_statements.append(statement)
        return FakeExecuteResult([])

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


class RecordingEmbeddingClient:
    model_name = "recording-embedding"
    dimension = EMBEDDING_DIMENSION

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.inputs.extend(texts)
        return [make_embedding() for _ in texts]

    async def embed_query(self, query: str) -> list[float]:
        self.inputs.append(query)
        return make_embedding()


def make_embedding() -> list[float]:
    return [0.0] * (EMBEDDING_DIMENSION - 1) + [1.0]


def test_count_reindex_statement_filters_workspace_and_source_uri() -> None:
    statement = build_count_reindex_chunks_statement(
        workspace_id="public",
        source_uri="llm_systems/flashattention.md",
    )
    compiled = str(statement)

    assert "document_chunks.workspace_id" in compiled
    assert "document_chunks.source_uri" in compiled


def test_fetch_reindex_batch_statement_orders_and_limits() -> None:
    statement = build_fetch_reindex_batch_statement(
        workspace_id="public",
        limit=10,
        offset=5,
    )
    compiled = str(statement)

    assert "ORDER BY document_chunks.source_uri" in compiled
    assert "LIMIT" in compiled
    assert "OFFSET" in compiled


@pytest.mark.asyncio
async def test_fetch_reindex_batch_maps_rows_to_targets() -> None:
    chunk_id = uuid.uuid4()
    session = FakeSession(
        fetch_batches=[
            [
                FakeRow(
                    chunk_id=chunk_id,
                    text="FlashAttention reduces memory traffic.",
                )
            ]
        ]
    )

    targets = await fetch_reindex_batch(
        session,  # type: ignore[arg-type]
        workspace_id="public",
        limit=1,
        offset=0,
    )

    assert targets == [
        ChunkEmbeddingTarget(
            chunk_id=chunk_id,
            text="FlashAttention reduces memory traffic.",
        )
    ]
    assert len(session.select_statements) == 1


@pytest.mark.asyncio
async def test_update_chunk_embeddings_updates_each_target() -> None:
    session = FakeSession()
    targets = [
        ChunkEmbeddingTarget(chunk_id=uuid.uuid4(), text="one"),
        ChunkEmbeddingTarget(chunk_id=uuid.uuid4(), text="two"),
    ]

    updated = await update_chunk_embeddings(
        session,  # type: ignore[arg-type]
        targets,
        [make_embedding(), make_embedding()],
    )

    assert updated == 2
    assert len(session.update_statements) == 2


@pytest.mark.asyncio
async def test_update_chunk_embeddings_rejects_count_mismatch() -> None:
    session = FakeSession()
    targets = [ChunkEmbeddingTarget(chunk_id=uuid.uuid4(), text="one")]

    with pytest.raises(ValueError, match="embedding count"):
        await update_chunk_embeddings(
            session,  # type: ignore[arg-type]
            targets,
            [],
        )


@pytest.mark.asyncio
async def test_reindex_embeddings_dry_run_counts_without_provider_calls() -> None:
    session = FakeSession(count=5)
    client = RecordingEmbeddingClient()

    stats = await reindex_embeddings(
        workspace_id=" public ",
        limit=2,
        dry_run=True,
        embedding_client=client,
        session_factory=lambda: FakeSessionContext(session),  # type: ignore[return-value]
    )

    assert stats.chunks_matched == 2
    assert stats.chunks_embedded == 0
    assert stats.chunks_updated == 0
    assert stats.model_name == "not-used-dry-run"
    assert client.inputs == []


@pytest.mark.asyncio
async def test_reindex_embeddings_write_embeds_and_updates_in_batches() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    session = FakeSession(
        count=2,
        fetch_batches=[
            [FakeRow(chunk_id=first_id, text="FlashAttention")],
            [FakeRow(chunk_id=second_id, text="PagedAttention")],
        ],
    )
    client = RecordingEmbeddingClient()

    stats = await reindex_embeddings(
        workspace_id="public",
        batch_size=1,
        dry_run=False,
        embedding_client=client,
        session_factory=lambda: FakeSessionContext(session),  # type: ignore[return-value]
    )

    assert stats.chunks_matched == 2
    assert stats.chunks_embedded == 2
    assert stats.chunks_updated == 2
    assert stats.model_name == "recording-embedding"
    assert client.inputs == ["FlashAttention", "PagedAttention"]
    assert len(session.select_statements) == 2
    assert len(session.update_statements) == 2


def test_format_reindex_stats_includes_mode_and_counts() -> None:
    output = format_reindex_stats(
        ReindexEmbeddingsStats(
            workspace_id="public",
            source_uri=None,
            model_name="test-model",
            chunks_matched=2,
            chunks_embedded=2,
            chunks_updated=2,
            dry_run=False,
            elapsed_seconds=1.234,
        )
    )

    assert "mode: write" in output
    assert "source_uri: all" in output
    assert "model: test-model" in output
    assert "chunks updated: 2" in output
    assert "elapsed: 1.23s" in output
