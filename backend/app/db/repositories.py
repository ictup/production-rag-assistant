import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    EMBEDDING_DIMENSION,
    ChatLog,
    ChatSession,
    Document,
    DocumentChunk,
    ExportJob,
    Workspace,
    WorkspaceAuditLog,
)
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
    session_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ChatLogListResult:
    total: int
    logs: list[ChatLog]


@dataclass(frozen=True)
class CreateChatSessionInput:
    workspace_id: str = "public"
    title: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ChatSessionListResult:
    total: int
    sessions: list[ChatSession]


@dataclass(frozen=True)
class CreateWorkspaceInput:
    id: str
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class UpdateWorkspaceInput:
    id: str
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None
    update_name: bool = False
    update_description: bool = False
    update_metadata: bool = False


@dataclass(frozen=True)
class ArchiveWorkspaceInput:
    id: str
    reason: str | None = None


@dataclass(frozen=True)
class CreateWorkspaceAuditLogInput:
    request_id: str
    actor_hash: str
    action: str
    workspace_ids: Sequence[str]
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CreateExportJobInput:
    request_id: str
    actor_hash: str
    workspace_id: str
    export_type: str
    format: str
    filters: dict[str, Any] | None = None


@dataclass(frozen=True)
class CreateWorkspaceResult:
    workspace: Workspace
    created: bool


@dataclass(frozen=True)
class BulkWorkspaceOperationResult:
    workspaces: list[Workspace]
    missing_ids: list[str]


@dataclass(frozen=True)
class WorkspaceListResult:
    total: int
    workspaces: list[Workspace]


@dataclass(frozen=True)
class WorkspaceAuditLogListResult:
    total: int
    audit_logs: list[WorkspaceAuditLog]


@dataclass(frozen=True)
class ExportJobListResult:
    total: int
    jobs: list[ExportJob]


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
class DocumentChunkSummary:
    id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: str
    chunk_index: int
    text: str
    token_count: int
    section_title: str | None
    page_number: int | None
    source_uri: str
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class DocumentListResult:
    total: int
    documents: list[DocumentSummary]


@dataclass(frozen=True)
class DocumentDetailResult:
    document: DocumentSummary
    chunks: list[DocumentChunkSummary]


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def require_text(value: str | None, field_name: str) -> str:
    normalized = normalize_optional_text(value)
    if normalized is None:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_workspace(
        self,
        workspace_input: CreateWorkspaceInput,
        *,
        commit: bool = False,
    ) -> CreateWorkspaceResult:
        workspace_id = workspace_input.id.strip()
        if not workspace_id:
            raise ValueError("workspace id must not be blank")

        existing_workspace = await self.get_workspace(workspace_id=workspace_id)
        if existing_workspace is not None:
            return CreateWorkspaceResult(
                workspace=existing_workspace,
                created=False,
            )

        workspace = Workspace(
            id=workspace_id,
            name=normalize_optional_text(workspace_input.name),
            description=normalize_optional_text(workspace_input.description),
            metadata_=dict(workspace_input.metadata or {}),
        )
        self.session.add(workspace)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return CreateWorkspaceResult(workspace=workspace, created=True)

    async def list_workspaces(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        workspace_ids: frozenset[str] | None = None,
        search: str | None = None,
        archived: bool | None = None,
    ) -> WorkspaceListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if workspace_ids == frozenset():
            return WorkspaceListResult(total=0, workspaces=[])

        filters = []
        if workspace_ids is not None:
            filters.append(Workspace.id.in_(sorted(workspace_ids)))
        if archived is True:
            filters.append(Workspace.archived_at.is_not(None))
        elif archived is False:
            filters.append(Workspace.archived_at.is_(None))
        search_query = normalize_optional_text(search)
        if search_query is not None:
            filters.append(
                or_(
                    Workspace.id.icontains(search_query, autoescape=True),
                    Workspace.name.icontains(search_query, autoescape=True),
                    Workspace.description.icontains(search_query, autoescape=True),
                )
            )

        total_statement = select(func.count()).select_from(Workspace).where(*filters)
        total = await self.session.scalar(total_statement)
        statement = (
            select(Workspace)
            .where(*filters)
            .order_by(Workspace.updated_at.desc(), Workspace.id.asc())
            .limit(limit)
            .offset(offset)
        )
        workspaces = list((await self.session.scalars(statement)).all())
        return WorkspaceListResult(
            total=int(total or 0),
            workspaces=workspaces,
        )

    async def get_workspace(self, *, workspace_id: str) -> Workspace | None:
        workspace_id = workspace_id.strip()
        if not workspace_id:
            raise ValueError("workspace id must not be blank")

        statement = select(Workspace).where(Workspace.id == workspace_id)
        return await self.session.scalar(statement)

    async def update_workspace(
        self,
        workspace_input: UpdateWorkspaceInput,
        *,
        commit: bool = False,
    ) -> Workspace | None:
        workspace_id = workspace_input.id.strip()
        if not workspace_id:
            raise ValueError("workspace id must not be blank")

        workspace = await self.get_workspace(workspace_id=workspace_id)
        if workspace is None:
            return None

        if workspace_input.update_name:
            workspace.name = normalize_optional_text(workspace_input.name)
        if workspace_input.update_description:
            workspace.description = normalize_optional_text(
                workspace_input.description
            )
        if workspace_input.update_metadata:
            workspace.metadata_ = dict(workspace_input.metadata or {})

        await self.session.flush()
        if commit:
            await self.session.commit()
        return workspace

    async def archive_workspace(
        self,
        workspace_input: ArchiveWorkspaceInput,
        *,
        commit: bool = False,
    ) -> Workspace | None:
        workspace_id = workspace_input.id.strip()
        if not workspace_id:
            raise ValueError("workspace id must not be blank")

        workspace = await self.get_workspace(workspace_id=workspace_id)
        if workspace is None:
            return None

        workspace.archived_at = datetime.now(UTC)
        workspace.archived_reason = normalize_optional_text(workspace_input.reason)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return workspace

    async def archive_workspaces(
        self,
        workspace_inputs: Sequence[ArchiveWorkspaceInput],
        *,
        commit: bool = False,
    ) -> BulkWorkspaceOperationResult:
        workspace_ids: list[str] = []
        reason_by_id: dict[str, str | None] = {}
        for workspace_input in workspace_inputs:
            workspace_id = workspace_input.id.strip()
            if not workspace_id:
                raise ValueError("workspace id must not be blank")
            if workspace_id not in reason_by_id:
                workspace_ids.append(workspace_id)
                reason_by_id[workspace_id] = normalize_optional_text(
                    workspace_input.reason
                )

        if not workspace_ids:
            raise ValueError("workspace ids must not be empty")

        statement = select(Workspace).where(Workspace.id.in_(workspace_ids))
        workspaces = list((await self.session.scalars(statement)).all())
        workspace_by_id = {workspace.id: workspace for workspace in workspaces}
        missing_ids = [
            workspace_id
            for workspace_id in workspace_ids
            if workspace_id not in workspace_by_id
        ]
        if missing_ids:
            return BulkWorkspaceOperationResult(workspaces=[], missing_ids=missing_ids)

        archived_at = datetime.now(UTC)
        updated_workspaces: list[Workspace] = []
        for workspace_id in workspace_ids:
            workspace = workspace_by_id[workspace_id]
            workspace.archived_at = archived_at
            workspace.archived_reason = reason_by_id[workspace_id]
            updated_workspaces.append(workspace)

        await self.session.flush()
        if commit:
            await self.session.commit()
        return BulkWorkspaceOperationResult(
            workspaces=updated_workspaces,
            missing_ids=[],
        )

    async def restore_workspace(
        self,
        *,
        workspace_id: str,
        commit: bool = False,
    ) -> Workspace | None:
        workspace_id = workspace_id.strip()
        if not workspace_id:
            raise ValueError("workspace id must not be blank")

        workspace = await self.get_workspace(workspace_id=workspace_id)
        if workspace is None:
            return None

        workspace.archived_at = None
        workspace.archived_reason = None
        await self.session.flush()
        if commit:
            await self.session.commit()
        return workspace

    async def restore_workspaces(
        self,
        *,
        workspace_ids: Sequence[str],
        commit: bool = False,
    ) -> BulkWorkspaceOperationResult:
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for workspace_id in workspace_ids:
            normalized_id = workspace_id.strip()
            if not normalized_id:
                raise ValueError("workspace id must not be blank")
            if normalized_id not in seen_ids:
                normalized_ids.append(normalized_id)
                seen_ids.add(normalized_id)

        if not normalized_ids:
            raise ValueError("workspace ids must not be empty")

        statement = select(Workspace).where(Workspace.id.in_(normalized_ids))
        workspaces = list((await self.session.scalars(statement)).all())
        workspace_by_id = {workspace.id: workspace for workspace in workspaces}
        missing_ids = [
            workspace_id
            for workspace_id in normalized_ids
            if workspace_id not in workspace_by_id
        ]
        if missing_ids:
            return BulkWorkspaceOperationResult(workspaces=[], missing_ids=missing_ids)

        restored_workspaces: list[Workspace] = []
        for workspace_id in normalized_ids:
            workspace = workspace_by_id[workspace_id]
            workspace.archived_at = None
            workspace.archived_reason = None
            restored_workspaces.append(workspace)

        await self.session.flush()
        if commit:
            await self.session.commit()
        return BulkWorkspaceOperationResult(
            workspaces=restored_workspaces,
            missing_ids=[],
        )

    async def create_workspace_audit_log(
        self,
        audit_input: CreateWorkspaceAuditLogInput,
        *,
        commit: bool = False,
    ) -> WorkspaceAuditLog:
        request_id = audit_input.request_id.strip()
        actor_hash = audit_input.actor_hash.strip()
        action = audit_input.action.strip()

        if not request_id:
            raise ValueError("request_id must not be blank")
        if not actor_hash:
            raise ValueError("actor_hash must not be blank")
        if not action:
            raise ValueError("action must not be blank")

        workspace_ids: list[str] = []
        seen_ids: set[str] = set()
        for workspace_id in audit_input.workspace_ids:
            normalized_id = workspace_id.strip()
            if not normalized_id:
                raise ValueError("workspace id must not be blank")
            if normalized_id not in seen_ids:
                workspace_ids.append(normalized_id)
                seen_ids.add(normalized_id)
        if not workspace_ids:
            raise ValueError("workspace ids must not be empty")

        audit_log = WorkspaceAuditLog(
            id=uuid.uuid4(),
            request_id=request_id,
            actor_hash=actor_hash,
            action=action,
            workspace_ids=workspace_ids,
            workspace_count=len(workspace_ids),
            metadata_=dict(audit_input.metadata or {}),
        )
        self.session.add(audit_log)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return audit_log

    async def list_workspace_audit_logs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        action: str | None = None,
        workspace_id: str | None = None,
        request_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        allowed_workspaces: frozenset[str] | None = None,
    ) -> WorkspaceAuditLogListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if allowed_workspaces == frozenset():
            return WorkspaceAuditLogListResult(total=0, audit_logs=[])

        filters = []
        normalized_action = normalize_optional_text(action)
        if normalized_action is not None:
            filters.append(WorkspaceAuditLog.action == normalized_action)

        normalized_workspace_id = normalize_optional_text(workspace_id)
        if normalized_workspace_id is not None:
            filters.append(
                WorkspaceAuditLog.workspace_ids.contains([normalized_workspace_id])
            )
        if allowed_workspaces is not None:
            filters.append(
                WorkspaceAuditLog.workspace_ids.contained_by(
                    sorted(allowed_workspaces)
                )
            )

        normalized_request_id = normalize_optional_text(request_id)
        if normalized_request_id is not None:
            filters.append(WorkspaceAuditLog.request_id == normalized_request_id)
        if created_from is not None:
            filters.append(WorkspaceAuditLog.created_at >= created_from)
        if created_to is not None:
            filters.append(WorkspaceAuditLog.created_at <= created_to)

        total_statement = (
            select(func.count()).select_from(WorkspaceAuditLog).where(*filters)
        )
        total = await self.session.scalar(total_statement)
        statement = (
            select(WorkspaceAuditLog)
            .where(*filters)
            .order_by(WorkspaceAuditLog.created_at.desc(), WorkspaceAuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        audit_logs = list((await self.session.scalars(statement)).all())
        return WorkspaceAuditLogListResult(
            total=int(total or 0),
            audit_logs=audit_logs,
        )


class ExportJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_export_job(
        self,
        export_input: CreateExportJobInput,
        *,
        commit: bool = False,
    ) -> ExportJob:
        request_id = require_text(export_input.request_id, "request_id")
        actor_hash = require_text(export_input.actor_hash, "actor_hash")
        workspace_id = require_text(export_input.workspace_id, "workspace_id")
        export_type = require_text(export_input.export_type, "export_type")
        export_format = require_text(export_input.format, "format")

        export_job = ExportJob(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            request_id=request_id,
            actor_hash=actor_hash,
            export_type=export_type,
            format=export_format,
            status="pending",
            filters_=dict(export_input.filters or {}),
        )
        self.session.add(export_job)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return export_job

    async def get_export_job(
        self,
        *,
        job_id: uuid.UUID,
        workspace_id: str | None = None,
    ) -> ExportJob | None:
        filters = [ExportJob.id == job_id]
        normalized_workspace_id = normalize_optional_text(workspace_id)
        if normalized_workspace_id is not None:
            filters.append(ExportJob.workspace_id == normalized_workspace_id)

        statement = select(ExportJob).where(*filters)
        return await self.session.scalar(statement)

    async def list_export_jobs(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        export_type: str | None = None,
    ) -> ExportJobListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")

        filters = [ExportJob.workspace_id == require_text(workspace_id, "workspace_id")]
        normalized_status = normalize_optional_text(status)
        if normalized_status is not None:
            filters.append(ExportJob.status == normalized_status)
        normalized_export_type = normalize_optional_text(export_type)
        if normalized_export_type is not None:
            filters.append(ExportJob.export_type == normalized_export_type)

        total_statement = select(func.count()).select_from(ExportJob).where(*filters)
        total = await self.session.scalar(total_statement)
        statement = (
            select(ExportJob)
            .where(*filters)
            .order_by(ExportJob.created_at.desc(), ExportJob.id.desc())
            .limit(limit)
            .offset(offset)
        )
        jobs = list((await self.session.scalars(statement)).all())
        return ExportJobListResult(total=int(total or 0), jobs=jobs)

    async def claim_next_pending_export_job(
        self,
        *,
        workspace_id: str | None = None,
        commit: bool = False,
    ) -> ExportJob | None:
        filters = [ExportJob.status == "pending"]
        normalized_workspace_id = normalize_optional_text(workspace_id)
        if normalized_workspace_id is not None:
            filters.append(ExportJob.workspace_id == normalized_workspace_id)

        statement = (
            select(ExportJob)
            .where(*filters)
            .order_by(ExportJob.created_at.asc(), ExportJob.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        export_job = await self.session.scalar(statement)
        if export_job is None:
            return None
        await self.mark_export_job_running(export_job=export_job, commit=commit)
        return export_job

    async def mark_export_job_running(
        self,
        *,
        job_id: uuid.UUID | None = None,
        export_job: ExportJob | None = None,
        commit: bool = False,
    ) -> ExportJob | None:
        job = export_job or await self._load_export_job(job_id)
        if job is None:
            return None
        if job.status != "pending":
            raise ValueError("export job must be pending to start")

        now = datetime.now(UTC)
        job.status = "running"
        job.started_at = now
        job.completed_at = None
        job.error_message = None
        job.updated_at = now
        await self.session.flush()
        if commit:
            await self.session.commit()
        return job

    async def complete_export_job(
        self,
        *,
        job_id: uuid.UUID,
        result_uri: str,
        result_media_type: str,
        result_size_bytes: int | None = None,
        commit: bool = False,
    ) -> ExportJob | None:
        job = await self._load_export_job(job_id)
        if job is None:
            return None
        if job.status != "running":
            raise ValueError("export job must be running to complete")

        normalized_result_uri = require_text(result_uri, "result_uri")
        normalized_media_type = require_text(result_media_type, "result_media_type")
        if result_size_bytes is not None and result_size_bytes < 0:
            raise ValueError("result_size_bytes must not be negative")

        now = datetime.now(UTC)
        job.status = "succeeded"
        job.result_uri = normalized_result_uri
        job.result_media_type = normalized_media_type
        job.result_size_bytes = result_size_bytes
        job.error_message = None
        job.completed_at = now
        job.updated_at = now
        await self.session.flush()
        if commit:
            await self.session.commit()
        return job

    async def fail_export_job(
        self,
        *,
        job_id: uuid.UUID,
        error_message: str,
        commit: bool = False,
    ) -> ExportJob | None:
        job = await self._load_export_job(job_id)
        if job is None:
            return None
        if job.status not in {"pending", "running"}:
            raise ValueError("export job must be pending or running to fail")

        now = datetime.now(UTC)
        job.status = "failed"
        job.error_message = require_text(error_message, "error_message")
        job.result_uri = None
        job.result_media_type = None
        job.result_size_bytes = None
        job.completed_at = now
        if job.started_at is None:
            job.started_at = now
        job.updated_at = now
        await self.session.flush()
        if commit:
            await self.session.commit()
        return job

    async def _load_export_job(self, job_id: uuid.UUID | None) -> ExportJob | None:
        if job_id is None:
            raise ValueError("job_id is required")
        return await self.get_export_job(job_id=job_id)


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
                self._build_document_summary(
                    document=document,
                    chunk_count=int(chunk_count or 0),
                )
                for document, chunk_count in rows
            ],
        )

    async def get_document_detail(
        self,
        *,
        document_id: uuid.UUID,
        workspace_id: str = "public",
    ) -> DocumentDetailResult | None:
        workspace_id = workspace_id.strip() or "public"
        document_statement = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
        document = await self.session.scalar(document_statement)
        if document is None:
            return None

        chunk_statement = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.workspace_id == workspace_id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
        chunks = list((await self.session.scalars(chunk_statement)).all())

        return DocumentDetailResult(
            document=self._build_document_summary(
                document=document,
                chunk_count=len(chunks),
            ),
            chunks=[self._build_chunk_summary(chunk) for chunk in chunks],
        )

    async def delete_document(
        self,
        *,
        document_id: uuid.UUID,
        workspace_id: str = "public",
        commit: bool = False,
    ) -> bool:
        workspace_id = workspace_id.strip() or "public"
        statement = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
        document = await self.session.scalar(statement)
        if document is None:
            return False

        await self.session.delete(document)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return True

    async def ingest_document(
        self,
        raw_document: RawDocument,
        chunks: Sequence[Chunk],
        *,
        content_hash: str | None = None,
        chunk_embeddings: Sequence[Sequence[float]] | None = None,
        commit: bool = False,
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
        if commit:
            await self.session.commit()

        return IngestDocumentResult(
            document_id=document_id,
            content_hash=resolved_hash,
            inserted=True,
            chunks_inserted=len(chunk_models),
        )

    @staticmethod
    def _build_document_summary(
        *,
        document: Document,
        chunk_count: int,
    ) -> DocumentSummary:
        return DocumentSummary(
            id=document.id,
            workspace_id=document.workspace_id,
            source_type=document.source_type,
            source_uri=document.source_uri,
            title=document.title,
            author=document.author,
            visibility=document.visibility,
            metadata=dict(document.metadata_),
            chunk_count=chunk_count,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    @staticmethod
    def _build_chunk_summary(chunk: DocumentChunk) -> DocumentChunkSummary:
        return DocumentChunkSummary(
            id=chunk.id,
            document_id=chunk.document_id,
            workspace_id=chunk.workspace_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            section_title=chunk.section_title,
            page_number=chunk.page_number,
            source_uri=chunk.source_uri,
            metadata=dict(chunk.metadata_),
            created_at=chunk.created_at,
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
            session_id=log_input.session_id,
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
        offset: int = 0,
        session_id: uuid.UUID | None = None,
        request_id: str | None = None,
        refusal_only: bool = False,
        citation_valid: bool | None = None,
    ) -> list[ChatLog]:
        workspace_id = workspace_id.strip() or "public"
        request_id = normalize_optional_text(request_id)
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")

        filters = [ChatLog.workspace_id == workspace_id]
        if session_id is not None:
            filters.append(ChatLog.session_id == session_id)
        if request_id is not None:
            filters.append(ChatLog.request_id == request_id)
        if refusal_only:
            filters.append(ChatLog.refusal.is_not(None))
        if citation_valid is not None:
            filters.append(ChatLog.citation_valid.is_(citation_valid))

        statement = (
            select(ChatLog)
            .where(*filters)
            .order_by(ChatLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_chat_logs_by_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: str = "public",
        limit: int = 50,
        offset: int = 0,
    ) -> ChatLogListResult:
        workspace_id = workspace_id.strip() or "public"
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")

        filters = (
            ChatLog.workspace_id == workspace_id,
            ChatLog.session_id == session_id,
        )
        total_statement = select(func.count()).select_from(ChatLog).where(*filters)
        total = await self.session.scalar(total_statement)

        statement = (
            select(ChatLog)
            .where(*filters)
            .order_by(ChatLog.created_at.asc(), ChatLog.id.asc())
            .limit(limit)
            .offset(offset)
        )
        logs = list((await self.session.scalars(statement)).all())
        return ChatLogListResult(total=int(total or 0), logs=logs)

    async def list_recent_chat_logs_by_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: str = "public",
        limit: int = 4,
    ) -> list[ChatLog]:
        workspace_id = workspace_id.strip() or "public"
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        statement = (
            select(ChatLog)
            .where(
                ChatLog.workspace_id == workspace_id,
                ChatLog.session_id == session_id,
            )
            .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
            .limit(limit)
        )
        logs = list((await self.session.scalars(statement)).all())
        return list(reversed(logs))


class ChatSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        session_input: CreateChatSessionInput,
        *,
        commit: bool = False,
    ) -> ChatSession:
        workspace_id = session_input.workspace_id.strip() or "public"
        title = (
            session_input.title.strip()
            if session_input.title is not None
            else None
        )
        if title == "":
            title = None

        chat_session = ChatSession(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            title=title,
            metadata_=dict(session_input.metadata or {}),
        )
        self.session.add(chat_session)
        await self.session.flush()
        if commit:
            await self.session.commit()
        return chat_session

    async def list_sessions(
        self,
        *,
        workspace_id: str = "public",
        limit: int = 20,
        offset: int = 0,
    ) -> ChatSessionListResult:
        workspace_id = workspace_id.strip() or "public"
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")

        total_statement = select(func.count()).select_from(ChatSession).where(
            ChatSession.workspace_id == workspace_id
        )
        total = await self.session.scalar(total_statement)
        statement = (
            select(ChatSession)
            .where(ChatSession.workspace_id == workspace_id)
            .order_by(
                ChatSession.updated_at.desc(),
                ChatSession.created_at.desc(),
                ChatSession.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        sessions = list((await self.session.scalars(statement)).all())
        return ChatSessionListResult(total=int(total or 0), sessions=sessions)

    async def get_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: str = "public",
    ) -> ChatSession | None:
        workspace_id = workspace_id.strip() or "public"
        statement = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.workspace_id == workspace_id,
        )
        return await self.session.scalar(statement)
