import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIMENSION = 1536


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
        onupdate=sql_text("now()"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_reason: Mapped[str | None] = mapped_column(Text)


workspaces_updated_at_idx = Index(
    "workspaces_updated_at_idx",
    Workspace.updated_at,
)
workspaces_archived_at_idx = Index(
    "workspaces_archived_at_idx",
    Workspace.archived_at,
)


class WorkspaceAuditLog(Base):
    __tablename__ = "workspace_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    actor_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    workspace_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )


workspace_audit_logs_created_at_idx = Index(
    "workspace_audit_logs_created_at_idx",
    WorkspaceAuditLog.created_at,
)
workspace_audit_logs_request_id_idx = Index(
    "workspace_audit_logs_request_id_idx",
    WorkspaceAuditLog.request_id,
)
workspace_audit_logs_workspace_ids_idx = Index(
    "workspace_audit_logs_workspace_ids_idx",
    WorkspaceAuditLog.workspace_ids,
    postgresql_using="gin",
)


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="export_jobs_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("workspaces.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    actor_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    export_type: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending",
        server_default=sql_text("'pending'"),
    )
    filters_: Mapped[dict[str, Any]] = mapped_column(
        "filters",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    result_uri: Mapped[str | None] = mapped_column(Text)
    result_media_type: Mapped[str | None] = mapped_column(Text)
    result_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
        onupdate=sql_text("now()"),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


export_jobs_workspace_created_at_idx = Index(
    "export_jobs_workspace_created_at_idx",
    ExportJob.workspace_id,
    ExportJob.created_at,
)
export_jobs_status_created_at_idx = Index(
    "export_jobs_status_created_at_idx",
    ExportJob.status,
    ExportJob.created_at,
)
export_jobs_request_id_idx = Index(
    "export_jobs_request_id_idx",
    ExportJob.request_id,
)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("workspaces.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        default="public",
        server_default=sql_text("'public'"),
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    visibility: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="public",
        server_default=sql_text("'public'"),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
        onupdate=sql_text("now()"),
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="document_chunks_document_id_chunk_index_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("workspaces.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        default="public",
        server_default=sql_text("'public'"),
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(section_title, '') || ' ' || \"text\")",
            persisted=True,
        ),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


document_chunks_embedding_hnsw_idx = Index(
    "document_chunks_embedding_hnsw",
    DocumentChunk.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
document_chunks_search_vector_idx = Index(
    "document_chunks_search_vector_idx",
    DocumentChunk.search_vector,
    postgresql_using="gin",
)
document_chunks_metadata_idx = Index(
    "document_chunks_metadata_idx",
    DocumentChunk.__table__.c["metadata"],
    postgresql_using="gin",
)
document_chunks_workspace_idx = Index(
    "document_chunks_workspace_idx",
    DocumentChunk.workspace_id,
)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("workspaces.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        default="public",
        server_default=sql_text("'public'"),
    )
    title: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
        onupdate=sql_text("now()"),
    )

    chat_logs: Mapped[list["ChatLog"]] = relationship(back_populates="session")


chat_sessions_workspace_updated_at_idx = Index(
    "chat_sessions_workspace_updated_at_idx",
    ChatSession.workspace_id,
    ChatSession.updated_at,
)


class ChatLog(Base):
    __tablename__ = "chat_logs"
    __table_args__ = (
        UniqueConstraint("request_id", name="chat_logs_request_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("workspaces.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        default="public",
        server_default=sql_text("'public'"),
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    retrieval: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    refusal: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    citation_valid: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )

    session: Mapped[ChatSession | None] = relationship(back_populates="chat_logs")


chat_logs_workspace_created_at_idx = Index(
    "chat_logs_workspace_created_at_idx",
    ChatLog.workspace_id,
    ChatLog.created_at,
)
chat_logs_session_created_at_idx = Index(
    "chat_logs_session_created_at_idx",
    ChatLog.session_id,
    ChatLog.created_at,
)
