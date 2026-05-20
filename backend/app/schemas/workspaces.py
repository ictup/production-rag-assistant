from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.db.models import Workspace, WorkspaceAuditLog
from backend.app.db.repositories import (
    BulkWorkspaceOperationResult,
    CreateWorkspaceResult,
    WorkspaceAuditLogListResult,
    WorkspaceListResult,
)

WorkspaceId = Annotated[str, Field(min_length=1, max_length=128)]
WorkspaceStatus = Literal["all", "active", "archived"]


class CreateWorkspaceRequest(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str | None = Field(default=None, max_length=256)
    description: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def workspace_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("workspace id must not be blank")
        return value

    @field_validator("name", "description")
    @classmethod
    def optional_text_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    description: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, Any] | None = None

    @field_validator("name", "description")
    @classmethod
    def optional_text_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ArchiveWorkspaceRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2048)

    @field_validator("reason")
    @classmethod
    def optional_reason_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class BulkArchiveWorkspacesRequest(BaseModel):
    ids: list[WorkspaceId] = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=2048)

    @field_validator("ids")
    @classmethod
    def workspace_ids_must_be_unique(cls, values: list[str]) -> list[str]:
        return normalize_workspace_ids(values)

    @field_validator("reason")
    @classmethod
    def optional_reason_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class BulkRestoreWorkspacesRequest(BaseModel):
    ids: list[WorkspaceId] = Field(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def workspace_ids_must_be_unique(cls, values: list[str]) -> list[str]:
        return normalize_workspace_ids(values)


class BulkMatchingWorkspacesRequest(BaseModel):
    q: str | None = Field(default=None, max_length=256)
    status: WorkspaceStatus = "all"
    expected_total: int = Field(ge=0, le=1000)
    confirm: bool = False

    @field_validator("q")
    @classmethod
    def optional_query_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class BulkArchiveMatchingWorkspacesRequest(BulkMatchingWorkspacesRequest):
    reason: str | None = Field(default=None, max_length=2048)

    @field_validator("reason")
    @classmethod
    def optional_reason_must_be_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class BulkRestoreMatchingWorkspacesRequest(BulkMatchingWorkspacesRequest):
    pass


def normalize_workspace_ids(values: list[str]) -> list[str]:
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workspace id must not be blank")
        if len(normalized) > 128:
            raise ValueError("workspace id must be 128 characters or fewer")
        if normalized not in seen_ids:
            normalized_ids.append(normalized)
            seen_ids.add(normalized)
    return normalized_ids


class WorkspaceItem(BaseModel):
    id: str
    name: str | None
    description: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    archived_reason: str | None

    @classmethod
    def from_model(cls, workspace: Workspace) -> "WorkspaceItem":
        return cls(
            id=workspace.id,
            name=workspace.name,
            description=workspace.description,
            metadata=dict(workspace.metadata_),
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
            archived_at=workspace.archived_at,
            archived_reason=workspace.archived_reason,
        )


class CreateWorkspaceResponse(BaseModel):
    workspace: WorkspaceItem
    created: bool

    @classmethod
    def from_result(cls, result: CreateWorkspaceResult) -> "CreateWorkspaceResponse":
        return cls(
            workspace=WorkspaceItem.from_model(result.workspace),
            created=result.created,
        )


class WorkspacesResponse(BaseModel):
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
    workspaces: list[WorkspaceItem]

    @classmethod
    def from_result(
        cls,
        *,
        limit: int,
        offset: int,
        result: WorkspaceListResult,
    ) -> "WorkspacesResponse":
        workspaces = [
            WorkspaceItem.from_model(workspace) for workspace in result.workspaces
        ]
        return cls(
            total=result.total,
            count=len(workspaces),
            limit=limit,
            offset=offset,
            workspaces=workspaces,
        )


class WorkspaceResponse(BaseModel):
    workspace: WorkspaceItem

    @classmethod
    def from_model(cls, workspace: Workspace) -> "WorkspaceResponse":
        return cls(workspace=WorkspaceItem.from_model(workspace))


class WorkspaceAuditLogItem(BaseModel):
    id: str
    request_id: str
    actor_hash: str
    action: str
    workspace_ids: list[str]
    workspace_count: int = Field(ge=0)
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_model(cls, audit_log: WorkspaceAuditLog) -> "WorkspaceAuditLogItem":
        return cls(
            id=str(audit_log.id),
            request_id=audit_log.request_id,
            actor_hash=audit_log.actor_hash,
            action=audit_log.action,
            workspace_ids=list(audit_log.workspace_ids),
            workspace_count=audit_log.workspace_count,
            metadata=dict(audit_log.metadata_),
            created_at=audit_log.created_at,
        )


class WorkspaceAuditLogsResponse(BaseModel):
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
    audit_logs: list[WorkspaceAuditLogItem]

    @classmethod
    def from_result(
        cls,
        *,
        limit: int,
        offset: int,
        result: WorkspaceAuditLogListResult,
    ) -> "WorkspaceAuditLogsResponse":
        audit_logs = [
            WorkspaceAuditLogItem.from_model(audit_log)
            for audit_log in result.audit_logs
        ]
        return cls(
            total=result.total,
            count=len(audit_logs),
            limit=limit,
            offset=offset,
            audit_logs=audit_logs,
        )


class BulkWorkspaceOperationResponse(BaseModel):
    action: str
    requested_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    workspaces: list[WorkspaceItem]

    @classmethod
    def from_result(
        cls,
        *,
        action: str,
        requested_count: int,
        result: BulkWorkspaceOperationResult,
    ) -> "BulkWorkspaceOperationResponse":
        workspaces = [
            WorkspaceItem.from_model(workspace) for workspace in result.workspaces
        ]
        return cls(
            action=action,
            requested_count=requested_count,
            updated_count=len(workspaces),
            workspaces=workspaces,
        )


class BulkWorkspacePreviewResponse(BaseModel):
    total: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    sample_limit: int = Field(gt=0)
    status: WorkspaceStatus
    q: str | None
    workspaces: list[WorkspaceItem]

    @classmethod
    def from_result(
        cls,
        *,
        sample_limit: int,
        workspace_status: WorkspaceStatus,
        q: str | None,
        result: WorkspaceListResult,
    ) -> "BulkWorkspacePreviewResponse":
        workspaces = [
            WorkspaceItem.from_model(workspace) for workspace in result.workspaces
        ]
        return cls(
            total=result.total,
            sample_count=len(workspaces),
            sample_limit=sample_limit,
            status=workspace_status,
            q=q,
            workspaces=workspaces,
        )
