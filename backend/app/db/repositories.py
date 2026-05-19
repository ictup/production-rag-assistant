import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import EMBEDDING_DIMENSION, ChatLog, Document, DocumentChunk
from backend.app.rag.embeddings import validate_embedding_batch
from ingestion.hashing import compute_content_hash
from ingestion.models import Chunk, RawDocument


@dataclass(frozen=True)
class IngestDocumentResult:
    document_id: uuid.UUID
    content_hash: str
    inserted: bool
    chunks_inserted: int
    reason: str | None = None


@dataclass(frozen=True)
class CreateChatLogInput:
    request_id: str
    workspace_id: str
    question: str
    answer: str
    sources: list[dict[str, Any]]
    retrieval: dict[str, Any]
    usage: dict[str, Any]
    refusal: dict[str, Any] | None
    citation_valid: bool | None
    latency_ms: int


@dataclass(frozen=True)
class DocumentSummary:
    id: uuid.UUID
    workspace_id: str
    source_type: str
    source_uri: str
    title: str
    author: str | None
    visibility: str
    metadata: dict[str, Any]
    chunk_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DocumentListResult:
    total: int
    documents: list[DocumentSummary]


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_document_id_by_hash(self, content_hash: str) -> uuid.UUID | None:
        statement = select(Document.id).where(Document.content_hash == content_hash)
        return await self.session.scalar(statement)

    async def list_documents(
        self,
        *,
        workspace_id: str = "public",
        limit: int = 20,
        offset: int = 0,
    ) -> DocumentListResult:
        workspace_id = workspace_id.strip() or "public"
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")

        total_statement = select(func.count()).select_from(Document).where(
            Document.workspace_id == workspace_id
        )
        total = await self.session.scalar(total_statement)

        chunk_counts = (
            select(
                DocumentChunk.document_id,
                func.count(DocumentChunk.id).label("chunk_count"),
            )
            .where(DocumentChunk.workspace_id == workspace_id)
            .group_by(DocumentChunk.document_id)
            .subquery()
        )
        statement = (
            select(
                Document,
                func.coalesce(chunk_counts.c.chunk_count, 0).label("chunk_count"),
            )
            .outerjoin(chunk_counts, chunk_counts.c.document_id == Document.id)
            .where(Document.workspace_id == workspace_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(statement)).all()

        return DocumentListResult(
            total=int(total or 0),
            documents=[
                DocumentSummary(
                    id=document.id,
                    workspace_id=document.workspace_id,
                    source_type=document.source_type,
                    source_uri=document.source_uri,
                    title=document.title,
                    author=document.author,
                    visibility=document.visibility,
                    metadata=dict(document.metadata_),
                    chunk_count=int(chunk_count or 0),
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                )
                for document, chunk_count in rows
            ],
        )

    async def ingest_document(
        self,
        raw_document: RawDocument,
        chunks: Sequence[Chunk],
        *,
        content_hash: str | None = None,
        chunk_embeddings: Sequence[Sequence[float]] | None = None,
    ) -> IngestDocumentResult:
        if not chunks:
            raise ValueError("cannot ingest a document without chunks")

        resolved_hash = content_hash or compute_content_hash(raw_document.text)
        existing_document_id = await self.get_document_id_by_hash(resolved_hash)
        if existing_document_id is not None:
            return IngestDocumentResult(
                document_id=existing_document_id,
                content_hash=resolved_hash,
                inserted=False,
                chunks_inserted=0,
                reason="duplicate_content_hash",
            )

        if chunk_embeddings is None:
            raise ValueError("chunk_embeddings are required for new documents")
        if len(chunk_embeddings) != len(chunks):
            raise ValueError(
                f"chunk_embeddings count {len(chunk_embeddings)} does not match "
                f"chunks count {len(chunks)}"
            )
        validate_embedding_batch(
            chunk_embeddings,
            expected_dimension=EMBEDDING_DIMENSION,
        )

        document_id = uuid.uuid4()
        document = Document(
            id=document_id,
            workspace_id=raw_document.workspace_id,
            source_type=raw_document.source_type,
            source_uri=raw_document.source_uri,
            title=raw_document.title,
            author=raw_document.author,
            content_hash=resolved_hash,
            visibility=raw_document.visibility,
            metadata_=dict(raw_document.metadata),
        )
        chunk_models = [
            self._build_chunk_model(
                document_id=document_id,
                chunk=chunk,
                embedding=list(embedding),
            )
            for chunk, embedding in zip(chunks, chunk_embeddings, strict=True)
        ]

        self.session.add(document)
        self.session.add_all(chunk_models)
        await self.session.flush()

        return IngestDocumentResult(
            document_id=document_id,
            content_hash=resolved_hash,
            inserted=True,
            chunks_inserted=len(chunk_models),
        )

    @staticmethod
    def _build_chunk_model(
        *,
        document_id: uuid.UUID,
        chunk: Chunk,
        embedding: list[float],
    ) -> DocumentChunk:
        return DocumentChunk(
            id=uuid.uuid4(),
            document_id=document_id,
            workspace_id=chunk.workspace_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            section_title=chunk.section_title,
            source_uri=chunk.source_uri,
            embedding=embedding,
            metadata_=dict(chunk.metadata),
        )


class ChatLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_chat_log(
        self,
        log_input: CreateChatLogInput,
        *,
        commit: bool = False,
    ) -> ChatLog:
        request_id = log_input.request_id.strip()
        workspace_id = log_input.workspace_id.strip() or "public"
        question = log_input.question.strip()

        if not request_id:
            raise ValueError("request_id must not be blank")
        if not question:
            raise ValueError("question must not be blank")
        if not log_input.answer.strip():
            raise ValueError("answer must not be blank")
        if log_input.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")

        chat_log = ChatLog(
            id=uuid.uuid4(),
            request_id=request_id,
            workspace_id=workspace_id,
            question=question,
            answer=log_input.answer,
            sources=list(log_input.sources),
            retrieval=dict(log_input.retrieval),
            usage=dict(log_input.usage),
            refusal=dict(log_input.refusal) if log_input.refusal is not None else None,
            citation_valid=log_input.citation_valid,
            latency_ms=log_input.latency_ms,
        )
        self.session.add(chat_log)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return chat_log

    async def list_recent_chat_logs(
        self,
        *,
        workspace_id: str = "public",
        limit: int = 10,
    ) -> list[ChatLog]:
        workspace_id = workspace_id.strip() or "public"
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        statement = (
            select(ChatLog)
            .where(ChatLog.workspace_id == workspace_id)
            .order_by(ChatLog.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())
