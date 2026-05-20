from datetime import datetime
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from backend.app.api.security import ApiPrincipal, require_api_key, resolve_workspace_id
from backend.app.api.workspace_validation import get_workspace_repository
from backend.app.core.request_id import get_request_id
from backend.app.db.repositories import (
    ArchiveWorkspaceInput,
    CreateWorkspaceAuditLogInput,
    CreateWorkspaceInput,
    UpdateWorkspaceInput,
    WorkspaceListResult,
    WorkspaceRepository,
)
from backend.app.schemas.workspaces import (
    ArchiveWorkspaceRequest,
    BulkArchiveMatchingWorkspacesRequest,
    BulkArchiveWorkspacesRequest,
    BulkRestoreMatchingWorkspacesRequest,
    BulkRestoreWorkspacesRequest,
    BulkWorkspaceOperationResponse,
    BulkWorkspacePreviewResponse,
    CreateWorkspaceRequest,
    CreateWorkspaceResponse,
    UpdateWorkspaceRequest,
    WorkspaceAuditLogsResponse,
    WorkspaceResponse,
    WorkspacesResponse,
    WorkspaceStatus,
)

router = APIRouter(tags=["workspaces"])


@router.post(
    "/workspaces",
    response_model=CreateWorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace(
    request: CreateWorkspaceRequest,
    response: Response,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> CreateWorkspaceResponse:
    workspace_id = resolve_workspace_id(principal, request.id)
    result = await repository.create_workspace(
        CreateWorkspaceInput(
            id=workspace_id,
            name=request.name,
            description=request.description,
            metadata=request.metadata,
        ),
        commit=True,
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return CreateWorkspaceResponse.from_result(result)


@router.get("/workspaces", response_model=WorkspacesResponse)
async def list_workspaces(
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=256)] = None,
    workspace_status: Annotated[
        WorkspaceStatus,
        Query(alias="status"),
    ] = "all",
) -> WorkspacesResponse:
    result = await repository.list_workspaces(
        workspace_ids=principal.allowed_workspaces,
        limit=limit,
        offset=offset,
        search=q,
        archived=workspace_status_to_archived_filter(workspace_status),
    )
    return WorkspacesResponse.from_result(
        limit=limit,
        offset=offset,
        result=result,
    )


@router.get("/workspaces/audit-logs", response_model=WorkspaceAuditLogsResponse)
async def list_workspace_audit_logs(
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query(max_length=64)] = None,
    workspace_id: Annotated[str | None, Query(max_length=128)] = None,
    request_id: Annotated[str | None, Query(max_length=256)] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> WorkspaceAuditLogsResponse:
    if created_from is not None and created_to is not None:
        if created_to < created_from:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="created_to must be greater than or equal to created_from",
            )

    normalized_workspace_id = (
        resolve_workspace_id(principal, workspace_id)
        if workspace_id is not None
        else None
    )
    result = await repository.list_workspace_audit_logs(
        limit=limit,
        offset=offset,
        action=action,
        workspace_id=normalized_workspace_id,
        request_id=request_id,
        created_from=created_from,
        created_to=created_to,
        allowed_workspaces=principal.allowed_workspaces,
    )
    return WorkspaceAuditLogsResponse.from_result(
        limit=limit,
        offset=offset,
        result=result,
    )


def workspace_status_to_archived_filter(
    workspace_status: WorkspaceStatus,
) -> bool | None:
    if workspace_status == "active":
        return False
    if workspace_status == "archived":
        return True
    return None


@router.get(
    "/workspaces/bulk/preview",
    response_model=BulkWorkspacePreviewResponse,
)
async def preview_bulk_workspaces(
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    q: Annotated[str | None, Query(max_length=256)] = None,
    workspace_status: Annotated[
        WorkspaceStatus,
        Query(alias="status"),
    ] = "all",
    sample_limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BulkWorkspacePreviewResponse:
    result = await repository.list_workspaces(
        workspace_ids=principal.allowed_workspaces,
        limit=sample_limit,
        offset=0,
        search=q,
        archived=workspace_status_to_archived_filter(workspace_status),
    )
    return BulkWorkspacePreviewResponse.from_result(
        sample_limit=sample_limit,
        workspace_status=workspace_status,
        q=q,
        result=result,
    )


@router.post(
    "/workspaces/bulk/archive-matching",
    response_model=BulkWorkspaceOperationResponse,
)
async def archive_matching_workspaces(
    request: BulkArchiveMatchingWorkspacesRequest,
    http_request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> BulkWorkspaceOperationResponse:
    matching_result = await load_confirmed_matching_workspaces(
        request=request,
        principal=principal,
        repository=repository,
    )
    if not matching_result.workspaces:
        return BulkWorkspaceOperationResponse(
            action="archive_matching",
            requested_count=0,
            updated_count=0,
            workspaces=[],
        )

    result = await repository.archive_workspaces(
        [
            ArchiveWorkspaceInput(id=workspace.id, reason=request.reason)
            for workspace in matching_result.workspaces
        ],
        commit=False,
    )
    raise_for_missing_bulk_workspaces(result.missing_ids)
    await record_workspace_operation_audit(
        repository=repository,
        principal=principal,
        request_id=get_request_id(http_request),
        action="archive_matching",
        workspace_ids=[workspace.id for workspace in result.workspaces],
        metadata={
            "mode": "matching_query",
            "q": request.q,
            "status": request.status,
            "expected_total": request.expected_total,
            "reason": request.reason,
        },
        commit=True,
    )
    return BulkWorkspaceOperationResponse.from_result(
        action="archive_matching",
        requested_count=len(matching_result.workspaces),
        result=result,
    )


@router.post(
    "/workspaces/bulk/restore-matching",
    response_model=BulkWorkspaceOperationResponse,
)
async def restore_matching_workspaces(
    request: BulkRestoreMatchingWorkspacesRequest,
    http_request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> BulkWorkspaceOperationResponse:
    matching_result = await load_confirmed_matching_workspaces(
        request=request,
        principal=principal,
        repository=repository,
    )
    if not matching_result.workspaces:
        return BulkWorkspaceOperationResponse(
            action="restore_matching",
            requested_count=0,
            updated_count=0,
            workspaces=[],
        )

    result = await repository.restore_workspaces(
        workspace_ids=[workspace.id for workspace in matching_result.workspaces],
        commit=False,
    )
    raise_for_missing_bulk_workspaces(result.missing_ids)
    await record_workspace_operation_audit(
        repository=repository,
        principal=principal,
        request_id=get_request_id(http_request),
        action="restore_matching",
        workspace_ids=[workspace.id for workspace in result.workspaces],
        metadata={
            "mode": "matching_query",
            "q": request.q,
            "status": request.status,
            "expected_total": request.expected_total,
        },
        commit=True,
    )
    return BulkWorkspaceOperationResponse.from_result(
        action="restore_matching",
        requested_count=len(matching_result.workspaces),
        result=result,
    )


async def load_confirmed_matching_workspaces(
    *,
    request: (
        BulkArchiveMatchingWorkspacesRequest | BulkRestoreMatchingWorkspacesRequest
    ),
    principal: ApiPrincipal,
    repository: WorkspaceRepository,
) -> WorkspaceListResult:
    if not request.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bulk matching operation confirmation required",
        )

    result = await repository.list_workspaces(
        workspace_ids=principal.allowed_workspaces,
        limit=max(request.expected_total, 1),
        offset=0,
        search=request.q,
        archived=workspace_status_to_archived_filter(request.status),
    )
    if result.total != request.expected_total:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "bulk preview total changed",
                "expected_total": request.expected_total,
                "current_total": result.total,
            },
        )
    return result


@router.post(
    "/workspaces/bulk/archive",
    response_model=BulkWorkspaceOperationResponse,
)
async def archive_workspaces(
    request: BulkArchiveWorkspacesRequest,
    http_request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> BulkWorkspaceOperationResponse:
    workspace_ids = resolve_bulk_workspace_ids(principal, request.ids)
    result = await repository.archive_workspaces(
        [
            ArchiveWorkspaceInput(id=workspace_id, reason=request.reason)
            for workspace_id in workspace_ids
        ],
        commit=False,
    )
    raise_for_missing_bulk_workspaces(result.missing_ids)
    await record_workspace_operation_audit(
        repository=repository,
        principal=principal,
        request_id=get_request_id(http_request),
        action="archive",
        workspace_ids=[workspace.id for workspace in result.workspaces],
        metadata={
            "mode": "explicit_ids",
            "requested_count": len(workspace_ids),
            "reason": request.reason,
        },
        commit=True,
    )
    return BulkWorkspaceOperationResponse.from_result(
        action="archive",
        requested_count=len(workspace_ids),
        result=result,
    )


@router.post(
    "/workspaces/bulk/restore",
    response_model=BulkWorkspaceOperationResponse,
)
async def restore_workspaces(
    request: BulkRestoreWorkspacesRequest,
    http_request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> BulkWorkspaceOperationResponse:
    workspace_ids = resolve_bulk_workspace_ids(principal, request.ids)
    result = await repository.restore_workspaces(
        workspace_ids=workspace_ids,
        commit=False,
    )
    raise_for_missing_bulk_workspaces(result.missing_ids)
    await record_workspace_operation_audit(
        repository=repository,
        principal=principal,
        request_id=get_request_id(http_request),
        action="restore",
        workspace_ids=[workspace.id for workspace in result.workspaces],
        metadata={
            "mode": "explicit_ids",
            "requested_count": len(workspace_ids),
        },
        commit=True,
    )
    return BulkWorkspaceOperationResponse.from_result(
        action="restore",
        requested_count=len(workspace_ids),
        result=result,
    )


def resolve_bulk_workspace_ids(
    principal: ApiPrincipal,
    workspace_ids: list[str],
) -> list[str]:
    resolved_ids: list[str] = []
    seen_ids: set[str] = set()
    for workspace_id in workspace_ids:
        resolved_id = resolve_workspace_id(principal, workspace_id)
        if resolved_id not in seen_ids:
            resolved_ids.append(resolved_id)
            seen_ids.add(resolved_id)
    return resolved_ids


def raise_for_missing_bulk_workspaces(missing_ids: list[str]) -> None:
    if not missing_ids:
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "message": "workspace not found",
            "workspace_ids": missing_ids,
        },
    )


async def record_workspace_operation_audit(
    *,
    repository: WorkspaceRepository,
    principal: ApiPrincipal,
    request_id: str,
    action: str,
    workspace_ids: list[str],
    metadata: dict,
    commit: bool,
) -> None:
    await repository.create_workspace_audit_log(
        CreateWorkspaceAuditLogInput(
            request_id=request_id,
            actor_hash=hash_principal_token(principal),
            action=action,
            workspace_ids=workspace_ids,
            metadata=metadata,
        ),
        commit=commit,
    )


def hash_principal_token(principal: ApiPrincipal) -> str:
    return sha256(principal.token.encode("utf-8")).hexdigest()


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    workspace = await repository.get_workspace(workspace_id=normalized_workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        )
    return WorkspaceResponse.from_model(workspace)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    updated_workspace = await repository.update_workspace(
        UpdateWorkspaceInput(
            id=normalized_workspace_id,
            name=request.name,
            description=request.description,
            metadata=request.metadata,
            update_name="name" in request.model_fields_set,
            update_description="description" in request.model_fields_set,
            update_metadata="metadata" in request.model_fields_set,
        ),
        commit=True,
    )
    if updated_workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        )
    return WorkspaceResponse.from_model(updated_workspace)


@router.post("/workspaces/{workspace_id}/archive", response_model=WorkspaceResponse)
async def archive_workspace(
    workspace_id: str,
    http_request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    request: ArchiveWorkspaceRequest | None = None,
) -> WorkspaceResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    archived_workspace = await repository.archive_workspace(
        ArchiveWorkspaceInput(
            id=normalized_workspace_id,
            reason=request.reason if request is not None else None,
        ),
        commit=False,
    )
    if archived_workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        )
    await record_workspace_operation_audit(
        repository=repository,
        principal=principal,
        request_id=get_request_id(http_request),
        action="archive",
        workspace_ids=[archived_workspace.id],
        metadata={
            "mode": "single_workspace",
            "reason": request.reason if request is not None else None,
        },
        commit=True,
    )
    return WorkspaceResponse.from_model(archived_workspace)


@router.post("/workspaces/{workspace_id}/restore", response_model=WorkspaceResponse)
async def restore_workspace(
    workspace_id: str,
    http_request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceResponse:
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    restored_workspace = await repository.restore_workspace(
        workspace_id=normalized_workspace_id,
        commit=False,
    )
    if restored_workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        )
    await record_workspace_operation_audit(
        repository=repository,
        principal=principal,
        request_id=get_request_id(http_request),
        action="restore",
        workspace_ids=[restored_workspace.id],
        metadata={"mode": "single_workspace"},
        commit=True,
    )
    return WorkspaceResponse.from_model(restored_workspace)
