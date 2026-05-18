import argparse
import asyncio
import time
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import EMBEDDING_DIMENSION, DocumentChunk
from backend.app.db.session import get_sessionmaker
from backend.app.rag.embeddings import (
    EmbeddingClient,
    build_embedding_client,
    validate_embedding_batch,
)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class ChunkEmbeddingTarget:
    chunk_id: uuid.UUID
    text: str


@dataclass
class ReindexEmbeddingsStats:
    workspace_id: str = "public"
    source_uri: str | None = None
    model_name: str = "not-used-dry-run"
    chunks_matched: int = 0
    chunks_embedded: int = 0
    chunks_updated: int = 0
    dry_run: bool = True
    elapsed_seconds: float = 0.0


def build_count_reindex_chunks_statement(
    *,
    workspace_id: str,
    source_uri: str | None = None,
) -> Select[tuple[int]]:
    statement = select(func.count()).select_from(DocumentChunk).where(
        DocumentChunk.workspace_id == workspace_id
    )
    if source_uri is not None:
        statement = statement.where(DocumentChunk.source_uri == source_uri)
    return statement


def build_fetch_reindex_batch_statement(
    *,
    workspace_id: str,
    source_uri: str | None = None,
    limit: int,
    offset: int,
) -> Select[tuple[uuid.UUID, str]]:
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    if offset < 0:
        raise ValueError("offset must not be negative")

    statement = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.text.label("text"),
        )
        .where(DocumentChunk.workspace_id == workspace_id)
        .order_by(DocumentChunk.source_uri, DocumentChunk.chunk_index, DocumentChunk.id)
        .limit(limit)
        .offset(offset)
    )
    if source_uri is not None:
        statement = statement.where(DocumentChunk.source_uri == source_uri)
    return statement


async def count_reindex_chunks(
    session: AsyncSession,
    *,
    workspace_id: str,
    source_uri: str | None = None,
) -> int:
    statement = build_count_reindex_chunks_statement(
        workspace_id=workspace_id,
        source_uri=source_uri,
    )
    result = await session.scalar(statement)
    return int(result or 0)


async def fetch_reindex_batch(
    session: AsyncSession,
    *,
    workspace_id: str,
    source_uri: str | None = None,
    limit: int,
    offset: int,
) -> list[ChunkEmbeddingTarget]:
    statement = build_fetch_reindex_batch_statement(
        workspace_id=workspace_id,
        source_uri=source_uri,
        limit=limit,
        offset=offset,
    )
    result = await session.execute(statement)
    targets: list[ChunkEmbeddingTarget] = []
    for row in result.all():
        mapping = row._mapping
        targets.append(
            ChunkEmbeddingTarget(
                chunk_id=mapping["chunk_id"],
                text=mapping["text"],
            )
        )
    return targets


async def update_chunk_embeddings(
    session: AsyncSession,
    targets: Sequence[ChunkEmbeddingTarget],
    embeddings: Sequence[Sequence[float]],
) -> int:
    if len(targets) != len(embeddings):
        raise ValueError(
            f"embedding count {len(embeddings)} does not match "
            f"target count {len(targets)}"
        )
    validate_embedding_batch(embeddings, expected_dimension=EMBEDDING_DIMENSION)

    for target, embedding in zip(targets, embeddings, strict=True):
        statement = (
            update(DocumentChunk)
            .where(DocumentChunk.id == target.chunk_id)
            .values(embedding=list(embedding))
        )
        await session.execute(statement)
    return len(targets)


async def reindex_embeddings(
    *,
    workspace_id: str = "public",
    source_uri: str | None = None,
    batch_size: int = 32,
    limit: int | None = None,
    dry_run: bool = True,
    embedding_client: EmbeddingClient | None = None,
    session_factory: SessionFactory | None = None,
) -> ReindexEmbeddingsStats:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")

    started_at = time.perf_counter()
    resolved_workspace_id = workspace_id.strip() or "public"
    resolved_source_uri = source_uri.strip() if source_uri is not None else None
    if resolved_source_uri == "":
        resolved_source_uri = None

    factory = session_factory or get_sessionmaker()
    client = embedding_client if not dry_run else None
    if not dry_run and client is None:
        client = build_embedding_client()

    stats = ReindexEmbeddingsStats(
        workspace_id=resolved_workspace_id,
        source_uri=resolved_source_uri,
        model_name=client.model_name if client is not None else "not-used-dry-run",
        dry_run=dry_run,
    )

    async with factory() as session:
        matched_count = await count_reindex_chunks(
            session,
            workspace_id=resolved_workspace_id,
            source_uri=resolved_source_uri,
        )
        stats.chunks_matched = (
            matched_count if limit is None else min(matched_count, limit)
        )
        if dry_run or stats.chunks_matched == 0:
            stats.elapsed_seconds = time.perf_counter() - started_at
            return stats

        offset = 0
        remaining = stats.chunks_matched
        while remaining > 0:
            current_batch_size = min(batch_size, remaining)
            targets = await fetch_reindex_batch(
                session,
                workspace_id=resolved_workspace_id,
                source_uri=resolved_source_uri,
                limit=current_batch_size,
                offset=offset,
            )
            await session.commit()
            if not targets:
                break

            embeddings = await client.embed_texts([target.text for target in targets])
            try:
                updated = await update_chunk_embeddings(session, targets, embeddings)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

            stats.chunks_embedded += len(embeddings)
            stats.chunks_updated += updated
            processed = len(targets)
            offset += processed
            remaining -= processed

    stats.elapsed_seconds = time.perf_counter() - started_at
    return stats


def format_reindex_stats(stats: ReindexEmbeddingsStats) -> str:
    mode = "dry-run" if stats.dry_run else "write"
    source_uri = stats.source_uri or "all"
    return "\n".join(
        [
            f"mode: {mode}",
            f"workspace_id: {stats.workspace_id}",
            f"source_uri: {source_uri}",
            f"model: {stats.model_name}",
            f"chunks matched: {stats.chunks_matched}",
            f"chunks embedded: {stats.chunks_embedded}",
            f"chunks updated: {stats.chunks_updated}",
            f"elapsed: {stats.elapsed_seconds:.2f}s",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild stored chunk embeddings with the configured provider."
    )
    parser.add_argument("--workspace-id", default="public")
    parser.add_argument("--source-uri", default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of chunks to re-embed.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist rebuilt embeddings. Defaults to dry-run.",
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stats = await reindex_embeddings(
        workspace_id=args.workspace_id,
        source_uri=args.source_uri,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=not args.write,
    )
    print(format_reindex_stats(stats))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
