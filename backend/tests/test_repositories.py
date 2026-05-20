import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from backend.app.db.models import (
    ChatLog,
    ChatSession,
    Document,
    DocumentChunk,
    ExportJob,
    Workspace,
    WorkspaceAuditLog,
)
from backend.app.db.repositories import (
    ArchiveWorkspaceInput,
    ChatLogRepository,
    ChatSessionRepository,
    CreateChatLogInput,
    CreateChatSessionInput,
    CreateExportJobInput,
    CreateWorkspaceAuditLogInput,
    CreateWorkspaceInput,
    DocumentRepository,
    ExportJobRepository,
    UpdateWorkspaceInput,
    WorkspaceRepository,
)
from ingestion.chunking import chunk_document
from ingestion.hashing import compute_content_hash
from ingestion.models import RawDocument


class FakeAsyncSession:
    def __init__(
        self,
        scalar_result: Any | None = None,
        scalars_result: list[Any] | None = None,
        execute_result: list[Any] | None = None,
    ) -> None:
        self.scalar_result = scalar_result
        self.scalars_result = scalars_result or []
        self.execute_result = execute_result or []
        self.scalar_statement: Any | None = None
        self.scalars_statement: Any | None = None
        self.execute_statement: Any | None = None
        self.added: list[Any] = []
        self.added_all: list[Any] = []
        self.deleted: list[Any] = []
        self.flushed = False
        self.committed = False

    async def scalar(self, statement: Any) -> Any | None:
        self.scalar_statement = statement
        return self.scalar_result

    async def scalars(self, statement: Any):
        self.scalars_statement = statement
        return FakeScalarResult(self.scalars_result)

    async def execute(self, statement: Any):
        self.execute_statement = statement
        return FakeExecuteResult(self.execute_result)

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    def add_all(self, instances: list[Any]) -> None:
        self.added_all.extend(instances)

    async def delete(self, instance: Any) -> None:
        self.deleted.append(instance)

    async def flush(self) -> None:
        self.flushed = True

    async def commit(self) -> None:
        self.committed = True


class FakeScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class FakeExecuteResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


def make_raw_document() -> RawDocument:
    return RawDocument(
        title="FlashAttention Notes",
        source_uri="data/raw/flashattention.md",
        text="# FlashAttention\n\nFlashAttention reduces HBM traffic.",
        metadata={"topic": "attention"},
        author="Dao et al.",
    )


def make_document_model() -> Document:
    return Document(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        workspace_id="tenant-a",
        source_type="markdown",
        source_uri="data/raw/flashattention.md",
        title="FlashAttention Notes",
        author="Dao et al.",
        content_hash="a" * 64,
        visibility="public",
        metadata_={"topic": "attention"},
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )


def make_chunk_model(
    *,
    chunk_index: int = 0,
    text: str = "FlashAttention reduces HBM traffic.",
) -> DocumentChunk:
    return DocumentChunk(
        id=uuid.UUID(f"22222222-2222-2222-2222-{chunk_index + 1:012d}"),
        document_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        workspace_id="tenant-a",
        chunk_index=chunk_index,
        text=text,
        token_count=5,
        section_title="FlashAttention",
        page_number=None,
        source_uri="data/raw/flashattention.md",
        embedding=make_embedding(),
        metadata_={"chunk": chunk_index},
        created_at=datetime(2026, 5, 18, 8, chunk_index, tzinfo=UTC),
    )


def make_embedding(dimension: int = 1536) -> list[float]:
    return [0.0] * (dimension - 1) + [1.0]


def make_chat_log_input(
    *,
    session_id: uuid.UUID | None = None,
) -> CreateChatLogInput:
    return CreateChatLogInput(
        request_id=" request-1 ",
        workspace_id=" public ",
        question=" What problem does FlashAttention solve? ",
        answer="FlashAttention reduces memory traffic. [1]",
        sources=[{"source_id": "1", "title": "FlashAttention Notes"}],
        retrieval={"mode": "hybrid_rrf_rerank"},
        usage={"model": "fake-llm", "latency_ms": 12},
        refusal=None,
        citation_valid=True,
        latency_ms=12,
        session_id=session_id,
    )


def make_chat_session_model() -> ChatSession:
    return ChatSession(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        workspace_id="tenant-a",
        title="GPU systems questions",
        metadata_={"topic": "systems"},
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )


def make_workspace_model(*, workspace_id: str = "tenant-a") -> Workspace:
    return Workspace(
        id=workspace_id,
        name="Tenant A",
        description="GPU systems team",
        metadata_={"tier": "internal"},
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )


def make_workspace_audit_log_model() -> WorkspaceAuditLog:
    return WorkspaceAuditLog(
        id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        request_id="request-1",
        actor_hash="a" * 64,
        action="archive",
        workspace_ids=["tenant-a", "tenant-b"],
        workspace_count=2,
        metadata_={"mode": "explicit_ids"},
        created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
    )


def make_export_job_model(*, status: str = "pending") -> ExportJob:
    return ExportJob(
        id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        workspace_id="tenant-a",
        request_id="request-1",
        actor_hash="a" * 64,
        export_type="chat_logs",
        format="jsonl",
        status=status,
        filters_={"limit": 1000},
        result_uri=None,
        result_media_type=None,
        result_size_bytes=None,
        error_message=None,
        created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        started_at=None,
        completed_at=None,
    )


@pytest.mark.asyncio
async def test_create_workspace_adds_workspace_model() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.create_workspace(
        CreateWorkspaceInput(
            id=" tenant-a ",
            name=" Tenant A ",
            description=" GPU systems team ",
            metadata={"tier": "internal"},
        )
    )

    assert result.created is True
    workspace = result.workspace
    assert isinstance(workspace, Workspace)
    assert workspace.id == "tenant-a"
    assert workspace.name == "Tenant A"
    assert workspace.description == "GPU systems team"
    assert workspace.metadata_ == {"tier": "internal"}
    assert session.added == [workspace]
    assert session.flushed is True
    assert session.committed is False


@pytest.mark.asyncio
async def test_create_workspace_returns_existing_workspace_without_insert() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(scalar_result=workspace)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.create_workspace(CreateWorkspaceInput(id="tenant-a"))

    assert result.created is False
    assert result.workspace == workspace
    assert session.added == []
    assert session.flushed is False


@pytest.mark.asyncio
async def test_create_workspace_can_commit_transaction() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    await repository.create_workspace(CreateWorkspaceInput(id="tenant-a"), commit=True)

    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_workspace_rejects_blank_id() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="workspace id"):
        await repository.create_workspace(CreateWorkspaceInput(id="   "))


@pytest.mark.asyncio
async def test_list_workspaces_filters_allowed_workspace_ids() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(
        scalar_result=1,
        scalars_result=[workspace],
    )
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.list_workspaces(
        workspace_ids=frozenset({"tenant-a"}),
        limit=10,
        offset=5,
    )

    assert result.total == 1
    assert result.workspaces == [workspace]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    assert "workspaces.id" in str(session.scalar_statement)
    compiled = str(session.scalars_statement)
    assert "workspaces.id" in compiled
    assert "ORDER BY workspaces.updated_at DESC" in compiled


@pytest.mark.asyncio
async def test_list_workspaces_filters_by_search_query() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(
        scalar_result=1,
        scalars_result=[workspace],
    )
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.list_workspaces(search=" Tenant ")

    assert result.total == 1
    assert result.workspaces == [workspace]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "lower(workspaces.id)" in compiled
    assert "lower(workspaces.name)" in compiled
    assert "lower(workspaces.description)" in compiled
    assert "ORDER BY workspaces.updated_at DESC" in compiled


@pytest.mark.asyncio
async def test_list_workspaces_filters_by_archived_status() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(
        scalar_result=1,
        scalars_result=[workspace],
    )
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.list_workspaces(archived=False)

    assert result.total == 1
    assert result.workspaces == [workspace]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "workspaces.archived_at IS NULL" in compiled


@pytest.mark.asyncio
async def test_list_workspaces_filters_by_archived_records() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(
        scalar_result=1,
        scalars_result=[workspace],
    )
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.list_workspaces(archived=True)

    assert result.total == 1
    assert result.workspaces == [workspace]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "workspaces.archived_at IS NOT NULL" in compiled


@pytest.mark.asyncio
async def test_list_workspaces_returns_empty_without_query_for_empty_set() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.list_workspaces(workspace_ids=frozenset())

    assert result.total == 0
    assert result.workspaces == []
    assert session.scalar_statement is None
    assert session.scalars_statement is None


@pytest.mark.asyncio
async def test_list_workspaces_rejects_invalid_pagination() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit"):
        await repository.list_workspaces(limit=0)

    with pytest.raises(ValueError, match="offset"):
        await repository.list_workspaces(offset=-1)


@pytest.mark.asyncio
async def test_get_workspace_queries_by_trimmed_id() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(scalar_result=workspace)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.get_workspace(workspace_id=" tenant-a ")

    assert result == workspace
    assert session.scalar_statement is not None
    assert "workspaces.id" in str(session.scalar_statement)


@pytest.mark.asyncio
async def test_update_workspace_updates_requested_fields() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(scalar_result=workspace)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.update_workspace(
        UpdateWorkspaceInput(
            id=" tenant-a ",
            name=" Updated Tenant ",
            description=" Updated description ",
            metadata={"tier": "external"},
            update_name=True,
            update_description=True,
            update_metadata=True,
        ),
        commit=True,
    )

    assert result == workspace
    assert workspace.name == "Updated Tenant"
    assert workspace.description == "Updated description"
    assert workspace.metadata_ == {"tier": "external"}
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_update_workspace_returns_none_for_missing_workspace() -> None:
    session = FakeAsyncSession(scalar_result=None)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.update_workspace(
        UpdateWorkspaceInput(id="tenant-a", name="Updated", update_name=True)
    )

    assert result is None
    assert session.flushed is False
    assert session.committed is False


@pytest.mark.asyncio
async def test_update_workspace_rejects_blank_id() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="workspace id"):
        await repository.update_workspace(UpdateWorkspaceInput(id="   "))


@pytest.mark.asyncio
async def test_archive_workspace_sets_archive_fields() -> None:
    workspace = make_workspace_model()
    session = FakeAsyncSession(scalar_result=workspace)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.archive_workspace(
        ArchiveWorkspaceInput(id=" tenant-a ", reason=" Retired tenant "),
        commit=True,
    )

    assert result == workspace
    assert workspace.archived_at is not None
    assert workspace.archived_reason == "Retired tenant"
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_archive_workspace_returns_none_for_missing_workspace() -> None:
    session = FakeAsyncSession(scalar_result=None)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.archive_workspace(
        ArchiveWorkspaceInput(id="tenant-a", reason="Retired tenant")
    )

    assert result is None
    assert session.flushed is False
    assert session.committed is False


@pytest.mark.asyncio
async def test_archive_workspaces_archives_records_in_one_commit() -> None:
    workspace_a = make_workspace_model(workspace_id="tenant-a")
    workspace_b = make_workspace_model(workspace_id="tenant-b")
    session = FakeAsyncSession(scalars_result=[workspace_b, workspace_a])
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.archive_workspaces(
        [
            ArchiveWorkspaceInput(id=" tenant-a ", reason=" Cleanup "),
            ArchiveWorkspaceInput(id="tenant-b", reason=" Cleanup "),
            ArchiveWorkspaceInput(id="tenant-a", reason="Duplicate"),
        ],
        commit=True,
    )

    assert result.missing_ids == []
    assert [workspace.id for workspace in result.workspaces] == ["tenant-a", "tenant-b"]
    assert workspace_a.archived_at is not None
    assert workspace_b.archived_at is not None
    assert workspace_a.archived_reason == "Cleanup"
    assert workspace_b.archived_reason == "Cleanup"
    assert session.flushed is True
    assert session.committed is True
    assert session.scalars_statement is not None
    assert "workspaces.id" in str(session.scalars_statement)


@pytest.mark.asyncio
async def test_archive_workspaces_returns_missing_ids_without_writing() -> None:
    workspace = make_workspace_model(workspace_id="tenant-a")
    session = FakeAsyncSession(scalars_result=[workspace])
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.archive_workspaces(
        [
            ArchiveWorkspaceInput(id="tenant-a", reason="Cleanup"),
            ArchiveWorkspaceInput(id="tenant-missing", reason="Cleanup"),
        ],
        commit=True,
    )

    assert result.workspaces == []
    assert result.missing_ids == ["tenant-missing"]
    assert workspace.archived_at is None
    assert session.flushed is False
    assert session.committed is False


@pytest.mark.asyncio
async def test_restore_workspace_clears_archive_fields() -> None:
    workspace = make_workspace_model()
    workspace.archived_at = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
    workspace.archived_reason = "Retired tenant"
    session = FakeAsyncSession(scalar_result=workspace)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.restore_workspace(
        workspace_id=" tenant-a ",
        commit=True,
    )

    assert result == workspace
    assert workspace.archived_at is None
    assert workspace.archived_reason is None
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_restore_workspace_returns_none_for_missing_workspace() -> None:
    session = FakeAsyncSession(scalar_result=None)
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.restore_workspace(workspace_id="tenant-a")

    assert result is None
    assert session.flushed is False
    assert session.committed is False


@pytest.mark.asyncio
async def test_restore_workspaces_restores_records_in_one_commit() -> None:
    workspace_a = make_workspace_model(workspace_id="tenant-a")
    workspace_b = make_workspace_model(workspace_id="tenant-b")
    workspace_a.archived_at = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
    workspace_a.archived_reason = "Cleanup"
    workspace_b.archived_at = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
    workspace_b.archived_reason = "Cleanup"
    session = FakeAsyncSession(scalars_result=[workspace_b, workspace_a])
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.restore_workspaces(
        workspace_ids=[" tenant-a ", "tenant-b", "tenant-a"],
        commit=True,
    )

    assert result.missing_ids == []
    assert [workspace.id for workspace in result.workspaces] == ["tenant-a", "tenant-b"]
    assert workspace_a.archived_at is None
    assert workspace_a.archived_reason is None
    assert workspace_b.archived_at is None
    assert workspace_b.archived_reason is None
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_restore_workspaces_returns_missing_ids_without_writing() -> None:
    workspace = make_workspace_model(workspace_id="tenant-a")
    workspace.archived_at = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
    workspace.archived_reason = "Cleanup"
    session = FakeAsyncSession(scalars_result=[workspace])
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.restore_workspaces(
        workspace_ids=["tenant-a", "tenant-missing"],
        commit=True,
    )

    assert result.workspaces == []
    assert result.missing_ids == ["tenant-missing"]
    assert workspace.archived_at is not None
    assert workspace.archived_reason == "Cleanup"
    assert session.flushed is False
    assert session.committed is False


@pytest.mark.asyncio
async def test_create_workspace_audit_log_adds_audit_model() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    audit_log = await repository.create_workspace_audit_log(
        CreateWorkspaceAuditLogInput(
            request_id=" request-1 ",
            actor_hash="a" * 64,
            action=" archive ",
            workspace_ids=[" tenant-a ", "tenant-b", "tenant-a"],
            metadata={"reason": "Cleanup"},
        ),
        commit=True,
    )

    assert isinstance(audit_log, WorkspaceAuditLog)
    assert audit_log.request_id == "request-1"
    assert audit_log.actor_hash == "a" * 64
    assert audit_log.action == "archive"
    assert audit_log.workspace_ids == ["tenant-a", "tenant-b"]
    assert audit_log.workspace_count == 2
    assert audit_log.metadata_ == {"reason": "Cleanup"}
    assert session.added == [audit_log]
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_workspace_audit_log_rejects_empty_workspace_ids() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="workspace ids"):
        await repository.create_workspace_audit_log(
            CreateWorkspaceAuditLogInput(
                request_id="request-1",
                actor_hash="a" * 64,
                action="archive",
                workspace_ids=[],
            )
        )

    assert session.added == []
    assert session.flushed is False


@pytest.mark.asyncio
async def test_list_workspace_audit_logs_applies_filters() -> None:
    audit_log = make_workspace_audit_log_model()
    session = FakeAsyncSession(scalar_result=1, scalars_result=[audit_log])
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]
    created_from = datetime(2026, 5, 20, 7, 0, tzinfo=UTC)
    created_to = datetime(2026, 5, 20, 9, 0, tzinfo=UTC)

    result = await repository.list_workspace_audit_logs(
        limit=10,
        offset=5,
        action=" archive ",
        workspace_id=" tenant-a ",
        request_id=" request-1 ",
        created_from=created_from,
        created_to=created_to,
        allowed_workspaces=frozenset({"tenant-a", "tenant-b"}),
    )

    assert result.total == 1
    assert result.audit_logs == [audit_log]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "workspace_audit_logs.action" in compiled
    assert "workspace_audit_logs.workspace_ids" in compiled
    assert "workspace_audit_logs.request_id" in compiled
    assert "workspace_audit_logs.created_at >=" in compiled
    assert "workspace_audit_logs.created_at <=" in compiled
    assert "ORDER BY workspace_audit_logs.created_at DESC" in compiled


@pytest.mark.asyncio
async def test_list_workspace_audit_logs_returns_empty_for_empty_allowed_set() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    result = await repository.list_workspace_audit_logs(
        allowed_workspaces=frozenset()
    )

    assert result.total == 0
    assert result.audit_logs == []
    assert session.scalar_statement is None
    assert session.scalars_statement is None


@pytest.mark.asyncio
async def test_list_workspace_audit_logs_rejects_invalid_pagination() -> None:
    session = FakeAsyncSession()
    repository = WorkspaceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit"):
        await repository.list_workspace_audit_logs(limit=0)

    with pytest.raises(ValueError, match="offset"):
        await repository.list_workspace_audit_logs(offset=-1)


@pytest.mark.asyncio
async def test_create_export_job_adds_pending_job_model() -> None:
    session = FakeAsyncSession()
    repository = ExportJobRepository(session)  # type: ignore[arg-type]

    export_job = await repository.create_export_job(
        CreateExportJobInput(
            request_id=" request-1 ",
            actor_hash="a" * 64,
            workspace_id=" tenant-a ",
            export_type=" chat_logs ",
            format=" jsonl ",
            filters={"limit": 1000, "refusal_only": True},
        ),
        commit=True,
    )

    assert isinstance(export_job, ExportJob)
    assert export_job.request_id == "request-1"
    assert export_job.actor_hash == "a" * 64
    assert export_job.workspace_id == "tenant-a"
    assert export_job.export_type == "chat_logs"
    assert export_job.format == "jsonl"
    assert export_job.status == "pending"
    assert export_job.filters_ == {"limit": 1000, "refusal_only": True}
    assert session.added == [export_job]
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_export_job_rejects_blank_required_fields() -> None:
    session = FakeAsyncSession()
    repository = ExportJobRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="workspace_id"):
        await repository.create_export_job(
            CreateExportJobInput(
                request_id="request-1",
                actor_hash="a" * 64,
                workspace_id=" ",
                export_type="chat_logs",
                format="jsonl",
            )
        )

    assert session.added == []
    assert session.flushed is False


@pytest.mark.asyncio
async def test_list_export_jobs_filters_workspace_status_and_type() -> None:
    export_job = make_export_job_model()
    session = FakeAsyncSession(scalar_result=1, scalars_result=[export_job])
    repository = ExportJobRepository(session)  # type: ignore[arg-type]

    result = await repository.list_export_jobs(
        workspace_id=" tenant-a ",
        limit=10,
        offset=5,
        status=" pending ",
        export_type=" chat_logs ",
    )

    assert result.total == 1
    assert result.jobs == [export_job]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "export_jobs.workspace_id" in compiled
    assert "export_jobs.status" in compiled
    assert "export_jobs.export_type" in compiled
    assert "ORDER BY export_jobs.created_at DESC" in compiled


@pytest.mark.asyncio
async def test_claim_next_pending_export_job_marks_job_running() -> None:
    export_job = make_export_job_model(status="pending")
    session = FakeAsyncSession(scalar_result=export_job)
    repository = ExportJobRepository(session)  # type: ignore[arg-type]

    result = await repository.claim_next_pending_export_job(commit=True)

    assert result == export_job
    assert export_job.status == "running"
    assert export_job.started_at is not None
    assert export_job.completed_at is None
    assert export_job.error_message is None
    assert session.scalar_statement is not None
    assert "export_jobs.status" in str(session.scalar_statement)
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_complete_export_job_marks_job_succeeded() -> None:
    export_job = make_export_job_model(status="running")
    export_job.started_at = datetime(2026, 5, 20, 8, 1, tzinfo=UTC)
    session = FakeAsyncSession(scalar_result=export_job)
    repository = ExportJobRepository(session)  # type: ignore[arg-type]

    result = await repository.complete_export_job(
        job_id=export_job.id,
        result_uri=" file://exports/chat-logs-public.jsonl ",
        result_media_type=" application/x-ndjson ",
        result_size_bytes=128,
        commit=True,
    )

    assert result == export_job
    assert export_job.status == "succeeded"
    assert export_job.result_uri == "file://exports/chat-logs-public.jsonl"
    assert export_job.result_media_type == "application/x-ndjson"
    assert export_job.result_size_bytes == 128
    assert export_job.error_message is None
    assert export_job.completed_at is not None
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_fail_export_job_marks_job_failed() -> None:
    export_job = make_export_job_model(status="pending")
    export_job.result_uri = "file://stale"
    export_job.result_media_type = "text/csv"
    export_job.result_size_bytes = 99
    session = FakeAsyncSession(scalar_result=export_job)
    repository = ExportJobRepository(session)  # type: ignore[arg-type]

    result = await repository.fail_export_job(
        job_id=export_job.id,
        error_message=" permission denied ",
        commit=True,
    )

    assert result == export_job
    assert export_job.status == "failed"
    assert export_job.error_message == "permission denied"
    assert export_job.result_uri is None
    assert export_job.result_media_type is None
    assert export_job.result_size_bytes is None
    assert export_job.started_at is not None
    assert export_job.completed_at is not None
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_export_job_repository_rejects_invalid_state_transitions() -> None:
    export_job = make_export_job_model(status="succeeded")
    session = FakeAsyncSession(scalar_result=export_job)
    repository = ExportJobRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="pending"):
        await repository.mark_export_job_running(job_id=export_job.id)

    export_job.status = "pending"
    with pytest.raises(ValueError, match="running"):
        await repository.complete_export_job(
            job_id=export_job.id,
            result_uri="file://exports/chat-logs-public.jsonl",
            result_media_type="application/x-ndjson",
        )


@pytest.mark.asyncio
async def test_get_document_id_by_hash_queries_document_hash() -> None:
    existing_id = uuid.uuid4()
    session = FakeAsyncSession(scalar_result=existing_id)
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    result = await repository.get_document_id_by_hash("a" * 64)

    assert result == existing_id
    assert session.scalar_statement is not None
    assert "documents.content_hash" in str(session.scalar_statement)


@pytest.mark.asyncio
async def test_list_documents_filters_workspace_and_returns_chunk_counts() -> None:
    document = make_document_model()
    session = FakeAsyncSession(
        scalar_result=1,  # type: ignore[arg-type]
        execute_result=[(document, 3)],
    )
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    result = await repository.list_documents(
        workspace_id=" tenant-a ",
        limit=10,
        offset=5,
    )

    assert result.total == 1
    assert len(result.documents) == 1
    summary = result.documents[0]
    assert summary.id == document.id
    assert summary.workspace_id == "tenant-a"
    assert summary.title == "FlashAttention Notes"
    assert summary.metadata == {"topic": "attention"}
    assert summary.chunk_count == 3
    assert session.scalar_statement is not None
    assert session.execute_statement is not None
    assert "documents.workspace_id" in str(session.scalar_statement)
    compiled = str(session.execute_statement)
    assert "documents.workspace_id" in compiled
    assert "ORDER BY documents.created_at DESC" in compiled


@pytest.mark.asyncio
async def test_list_documents_rejects_invalid_pagination() -> None:
    session = FakeAsyncSession()
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit"):
        await repository.list_documents(limit=0)

    with pytest.raises(ValueError, match="offset"):
        await repository.list_documents(offset=-1)


@pytest.mark.asyncio
async def test_get_document_detail_returns_document_and_ordered_chunks() -> None:
    document = make_document_model()
    chunks = [
        make_chunk_model(chunk_index=0),
        make_chunk_model(chunk_index=1, text="It uses tiling for exact attention."),
    ]
    session = FakeAsyncSession(
        scalar_result=document,
        scalars_result=chunks,
    )
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    result = await repository.get_document_detail(
        document_id=document.id,
        workspace_id=" tenant-a ",
    )

    assert result is not None
    assert result.document.id == document.id
    assert result.document.workspace_id == "tenant-a"
    assert result.document.chunk_count == 2
    assert [chunk.chunk_index for chunk in result.chunks] == [0, 1]
    assert result.chunks[0].text == "FlashAttention reduces HBM traffic."
    assert result.chunks[0].metadata == {"chunk": 0}
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    assert "documents.workspace_id" in str(session.scalar_statement)
    compiled = str(session.scalars_statement)
    assert "document_chunks.workspace_id" in compiled
    assert "ORDER BY document_chunks.chunk_index ASC" in compiled


@pytest.mark.asyncio
async def test_get_document_detail_returns_none_for_missing_document() -> None:
    session = FakeAsyncSession(scalar_result=None)
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    result = await repository.get_document_detail(
        document_id=uuid.uuid4(),
        workspace_id="tenant-a",
    )

    assert result is None
    assert session.scalar_statement is not None
    assert session.scalars_statement is None


@pytest.mark.asyncio
async def test_delete_document_deletes_matching_workspace_document() -> None:
    document = make_document_model()
    session = FakeAsyncSession(scalar_result=document)
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    result = await repository.delete_document(
        document_id=document.id,
        workspace_id=" tenant-a ",
        commit=True,
    )

    assert result is True
    assert session.deleted == [document]
    assert session.flushed is True
    assert session.committed is True
    assert session.scalar_statement is not None
    assert "documents.workspace_id" in str(session.scalar_statement)


@pytest.mark.asyncio
async def test_delete_document_returns_false_for_missing_document() -> None:
    session = FakeAsyncSession(scalar_result=None)
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    result = await repository.delete_document(
        document_id=uuid.uuid4(),
        workspace_id="tenant-a",
        commit=True,
    )

    assert result is False
    assert session.deleted == []
    assert session.flushed is False
    assert session.committed is False


@pytest.mark.asyncio
async def test_ingest_document_skips_existing_content_hash() -> None:
    existing_id = uuid.uuid4()
    session = FakeAsyncSession(scalar_result=existing_id)
    repository = DocumentRepository(session)  # type: ignore[arg-type]
    raw_document = make_raw_document()
    chunks = chunk_document(raw_document, chunk_size_tokens=40, chunk_overlap_tokens=5)

    result = await repository.ingest_document(raw_document, chunks)

    assert result.document_id == existing_id
    assert result.inserted is False
    assert result.chunks_inserted == 0
    assert result.reason == "duplicate_content_hash"
    assert session.added == []
    assert session.added_all == []
    assert session.flushed is False


@pytest.mark.asyncio
async def test_ingest_document_adds_document_and_chunks() -> None:
    session = FakeAsyncSession()
    repository = DocumentRepository(session)  # type: ignore[arg-type]
    raw_document = make_raw_document()
    chunks = chunk_document(raw_document, chunk_size_tokens=40, chunk_overlap_tokens=5)
    embeddings = [make_embedding() for _ in chunks]

    result = await repository.ingest_document(
        raw_document,
        chunks,
        chunk_embeddings=embeddings,
    )

    assert result.inserted is True
    assert result.chunks_inserted == len(chunks)
    assert result.content_hash == compute_content_hash(raw_document.text)
    assert session.flushed is True

    document = session.added[0]
    assert isinstance(document, Document)
    assert document.id == result.document_id
    assert document.title == raw_document.title
    assert document.content_hash == result.content_hash
    assert document.metadata_ == {"topic": "attention"}

    chunk_model = session.added_all[0]
    assert isinstance(chunk_model, DocumentChunk)
    assert chunk_model.document_id == result.document_id
    assert chunk_model.chunk_index == chunks[0].chunk_index
    assert chunk_model.text == chunks[0].text
    assert chunk_model.embedding == embeddings[0]
    assert chunk_model.metadata_ == {"topic": "attention"}


@pytest.mark.asyncio
async def test_ingest_document_can_commit_transaction() -> None:
    session = FakeAsyncSession()
    repository = DocumentRepository(session)  # type: ignore[arg-type]
    raw_document = make_raw_document()
    chunks = chunk_document(raw_document, chunk_size_tokens=40, chunk_overlap_tokens=5)
    embeddings = [make_embedding() for _ in chunks]

    await repository.ingest_document(
        raw_document,
        chunks,
        chunk_embeddings=embeddings,
        commit=True,
    )

    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_ingest_document_requires_embeddings_for_new_document() -> None:
    session = FakeAsyncSession()
    repository = DocumentRepository(session)  # type: ignore[arg-type]
    raw_document = make_raw_document()
    chunks = chunk_document(raw_document, chunk_size_tokens=40, chunk_overlap_tokens=5)

    with pytest.raises(ValueError, match="chunk_embeddings are required"):
        await repository.ingest_document(raw_document, chunks)


@pytest.mark.asyncio
async def test_ingest_document_rejects_embedding_count_mismatch() -> None:
    session = FakeAsyncSession()
    repository = DocumentRepository(session)  # type: ignore[arg-type]
    raw_document = make_raw_document()
    chunks = chunk_document(raw_document, chunk_size_tokens=40, chunk_overlap_tokens=5)

    with pytest.raises(ValueError, match="does not match"):
        await repository.ingest_document(
            raw_document,
            chunks,
            chunk_embeddings=[],
        )


@pytest.mark.asyncio
async def test_ingest_document_rejects_embedding_dimension_mismatch() -> None:
    session = FakeAsyncSession()
    repository = DocumentRepository(session)  # type: ignore[arg-type]
    raw_document = make_raw_document()
    chunks = chunk_document(raw_document, chunk_size_tokens=40, chunk_overlap_tokens=5)

    with pytest.raises(ValueError, match="does not match"):
        await repository.ingest_document(
            raw_document,
            chunks,
            chunk_embeddings=[[0.1, 0.2] for _ in chunks],
        )


@pytest.mark.asyncio
async def test_ingest_document_rejects_empty_chunk_list() -> None:
    session = FakeAsyncSession()
    repository = DocumentRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="without chunks"):
        await repository.ingest_document(make_raw_document(), [])


@pytest.mark.asyncio
async def test_create_chat_log_adds_chat_log_model() -> None:
    session = FakeAsyncSession()
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    chat_log = await repository.create_chat_log(make_chat_log_input())

    assert isinstance(chat_log, ChatLog)
    assert chat_log.request_id == "request-1"
    assert chat_log.workspace_id == "public"
    assert chat_log.session_id is None
    assert chat_log.question == "What problem does FlashAttention solve?"
    assert chat_log.answer == "FlashAttention reduces memory traffic. [1]"
    assert chat_log.sources == [{"source_id": "1", "title": "FlashAttention Notes"}]
    assert chat_log.retrieval == {"mode": "hybrid_rrf_rerank"}
    assert chat_log.usage == {"model": "fake-llm", "latency_ms": 12}
    assert chat_log.refusal is None
    assert chat_log.citation_valid is True
    assert chat_log.latency_ms == 12
    assert session.added == [chat_log]
    assert session.flushed is True
    assert session.committed is False


@pytest.mark.asyncio
async def test_create_chat_log_can_attach_session_id() -> None:
    session = FakeAsyncSession()
    repository = ChatLogRepository(session)  # type: ignore[arg-type]
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")

    chat_log = await repository.create_chat_log(
        make_chat_log_input(session_id=session_id)
    )

    assert chat_log.session_id == session_id


@pytest.mark.asyncio
async def test_create_chat_log_can_commit_transaction() -> None:
    session = FakeAsyncSession()
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    await repository.create_chat_log(make_chat_log_input(), commit=True)

    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("request_id", "   ", "request_id"),
        ("question", "   ", "question"),
        ("answer", "   ", "answer"),
        ("latency_ms", -1, "latency_ms"),
    ],
)
async def test_create_chat_log_rejects_invalid_input(
    field: str,
    value: Any,
    error: str,
) -> None:
    session = FakeAsyncSession()
    repository = ChatLogRepository(session)  # type: ignore[arg-type]
    log_input = make_chat_log_input()
    invalid_input = CreateChatLogInput(
        **{
            **log_input.__dict__,
            field: value,
        }
    )

    with pytest.raises(ValueError, match=error):
        await repository.create_chat_log(invalid_input)


@pytest.mark.asyncio
async def test_list_recent_chat_logs_filters_workspace_and_limits_results() -> None:
    chat_log = ChatLog(
        request_id="request-1",
        workspace_id="public",
        question="What is FlashAttention?",
        answer="FlashAttention is IO-aware. [1]",
        sources=[],
        retrieval={},
        usage={},
        refusal=None,
        citation_valid=True,
        latency_ms=12,
    )
    session = FakeAsyncSession(scalars_result=[chat_log])
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    result = await repository.list_recent_chat_logs(
        workspace_id=" public ",
        limit=3,
        offset=2,
    )

    assert result == [chat_log]
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "chat_logs.workspace_id" in compiled
    assert "ORDER BY chat_logs.created_at DESC" in compiled
    assert "LIMIT" in compiled
    assert "OFFSET" in compiled


@pytest.mark.asyncio
async def test_list_recent_chat_logs_applies_audit_filters() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    chat_log = ChatLog(
        request_id="request-1",
        workspace_id="tenant-a",
        session_id=session_id,
        question="What is FlashAttention?",
        answer="FlashAttention is IO-aware. [1]",
        sources=[],
        retrieval={},
        usage={},
        refusal={"reason": "low_retrieval_confidence"},
        citation_valid=False,
        latency_ms=12,
    )
    session = FakeAsyncSession(scalars_result=[chat_log])
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    result = await repository.list_recent_chat_logs(
        workspace_id="tenant-a",
        limit=3,
        offset=1,
        session_id=session_id,
        request_id=" request-1 ",
        refusal_only=True,
        citation_valid=False,
    )

    assert result == [chat_log]
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "chat_logs.session_id" in compiled
    assert "chat_logs.request_id" in compiled
    assert "chat_logs.refusal IS NOT NULL" in compiled
    assert "chat_logs.citation_valid IS false" in compiled


@pytest.mark.asyncio
async def test_list_recent_chat_logs_rejects_invalid_limit() -> None:
    session = FakeAsyncSession()
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit"):
        await repository.list_recent_chat_logs(limit=0)

    with pytest.raises(ValueError, match="offset"):
        await repository.list_recent_chat_logs(offset=-1)


@pytest.mark.asyncio
async def test_list_chat_logs_by_session_filters_workspace_and_session() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    chat_log = ChatLog(
        request_id="request-1",
        workspace_id="tenant-a",
        session_id=session_id,
        question="What is FlashAttention?",
        answer="FlashAttention is IO-aware. [1]",
        sources=[],
        retrieval={},
        usage={},
        refusal=None,
        citation_valid=True,
        latency_ms=12,
    )
    session = FakeAsyncSession(
        scalar_result=7,
        scalars_result=[chat_log],
    )
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    result = await repository.list_chat_logs_by_session(
        session_id=session_id,
        workspace_id=" tenant-a ",
        limit=3,
        offset=6,
    )

    assert result.total == 7
    assert result.logs == [chat_log]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    assert "chat_logs.workspace_id" in str(session.scalar_statement)
    assert "chat_logs.session_id" in str(session.scalar_statement)
    compiled = str(session.scalars_statement)
    assert "chat_logs.workspace_id" in compiled
    assert "chat_logs.session_id" in compiled
    assert "ORDER BY chat_logs.created_at ASC" in compiled


@pytest.mark.asyncio
async def test_list_chat_logs_by_session_rejects_invalid_pagination() -> None:
    session = FakeAsyncSession()
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit"):
        await repository.list_chat_logs_by_session(
            session_id=uuid.uuid4(),
            limit=0,
        )

    with pytest.raises(ValueError, match="offset"):
        await repository.list_chat_logs_by_session(
            session_id=uuid.uuid4(),
            offset=-1,
        )


@pytest.mark.asyncio
async def test_list_recent_chat_logs_by_session_orders_recent_logs() -> None:
    session_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    newer_log = ChatLog(
        id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        request_id="request-newer",
        workspace_id="tenant-a",
        session_id=session_id,
        question="What problem does it solve?",
        answer="It reduces memory traffic. [1]",
        sources=[],
        retrieval={},
        usage={},
        refusal=None,
        citation_valid=True,
        latency_ms=12,
    )
    older_log = ChatLog(
        id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        request_id="request-older",
        workspace_id="tenant-a",
        session_id=session_id,
        question="What is FlashAttention?",
        answer="FlashAttention is IO-aware attention. [1]",
        sources=[],
        retrieval={},
        usage={},
        refusal=None,
        citation_valid=True,
        latency_ms=12,
    )
    session = FakeAsyncSession(scalars_result=[newer_log, older_log])
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    result = await repository.list_recent_chat_logs_by_session(
        session_id=session_id,
        workspace_id=" tenant-a ",
        limit=2,
    )

    assert result == [older_log, newer_log]
    assert session.scalars_statement is not None
    compiled = str(session.scalars_statement)
    assert "chat_logs.workspace_id" in compiled
    assert "chat_logs.session_id" in compiled
    assert "ORDER BY chat_logs.created_at DESC" in compiled


@pytest.mark.asyncio
async def test_list_recent_chat_logs_by_session_rejects_invalid_limit() -> None:
    session = FakeAsyncSession()
    repository = ChatLogRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit"):
        await repository.list_recent_chat_logs_by_session(
            session_id=uuid.uuid4(),
            limit=0,
        )


@pytest.mark.asyncio
async def test_create_chat_session_adds_session_model() -> None:
    session = FakeAsyncSession()
    repository = ChatSessionRepository(session)  # type: ignore[arg-type]

    chat_session = await repository.create_session(
        CreateChatSessionInput(
            workspace_id=" tenant-a ",
            title=" GPU systems questions ",
            metadata={"topic": "systems"},
        )
    )

    assert isinstance(chat_session, ChatSession)
    assert chat_session.workspace_id == "tenant-a"
    assert chat_session.title == "GPU systems questions"
    assert chat_session.metadata_ == {"topic": "systems"}
    assert session.added == [chat_session]
    assert session.flushed is True
    assert session.committed is False


@pytest.mark.asyncio
async def test_create_chat_session_can_commit_transaction() -> None:
    session = FakeAsyncSession()
    repository = ChatSessionRepository(session)  # type: ignore[arg-type]

    await repository.create_session(CreateChatSessionInput(), commit=True)

    assert session.flushed is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_list_chat_sessions_filters_workspace_and_paginates() -> None:
    chat_session = make_chat_session_model()
    session = FakeAsyncSession(
        scalar_result=1,
        scalars_result=[chat_session],
    )
    repository = ChatSessionRepository(session)  # type: ignore[arg-type]

    result = await repository.list_sessions(
        workspace_id=" tenant-a ",
        limit=10,
        offset=5,
    )

    assert result.total == 1
    assert result.sessions == [chat_session]
    assert session.scalar_statement is not None
    assert session.scalars_statement is not None
    assert "chat_sessions.workspace_id" in str(session.scalar_statement)
    compiled = str(session.scalars_statement)
    assert "chat_sessions.workspace_id" in compiled
    assert "ORDER BY chat_sessions.updated_at DESC" in compiled


@pytest.mark.asyncio
async def test_list_chat_sessions_rejects_invalid_pagination() -> None:
    session = FakeAsyncSession()
    repository = ChatSessionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit"):
        await repository.list_sessions(limit=0)

    with pytest.raises(ValueError, match="offset"):
        await repository.list_sessions(offset=-1)


@pytest.mark.asyncio
async def test_get_chat_session_filters_workspace_and_id() -> None:
    chat_session = make_chat_session_model()
    session = FakeAsyncSession(scalar_result=chat_session)
    repository = ChatSessionRepository(session)  # type: ignore[arg-type]

    result = await repository.get_session(
        session_id=chat_session.id,
        workspace_id=" tenant-a ",
    )

    assert result == chat_session
    assert session.scalar_statement is not None
    compiled = str(session.scalar_statement)
    assert "chat_sessions.id" in compiled
    assert "chat_sessions.workspace_id" in compiled
