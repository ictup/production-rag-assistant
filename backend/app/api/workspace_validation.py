from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Workspace
from backend.app.db.repositories import WorkspaceRepository
from backend.app.db.session import get_db_session


async def get_workspace_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceRepository:
    return WorkspaceRepository(session=session)


async def require_existing_workspace(
    *,
    workspace_id: str,
    repository: WorkspaceRepository,
) -> Workspace:
    workspace = await repository.get_workspace(workspace_id=workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        )
    return workspace


async def require_active_workspace(
    *,
    workspace_id: str,
    repository: WorkspaceRepository,
) -> Workspace:
    workspace = await require_existing_workspace(
        workspace_id=workspace_id,
        repository=repository,
    )
    if getattr(workspace, "archived_at", None) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="workspace archived",
        )
    return workspace
