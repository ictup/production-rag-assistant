from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api.workspace_validation import (
    require_active_workspace,
    require_existing_workspace,
)


class FakeWorkspaceRepository:
    def __init__(self, workspace: object | None) -> None:
        self.workspace = workspace
        self.get_calls: list[str] = []

    async def get_workspace(self, *, workspace_id: str):
        self.get_calls.append(workspace_id)
        return self.workspace


@pytest.mark.asyncio
async def test_require_existing_workspace_returns_workspace() -> None:
    workspace = SimpleNamespace(id="tenant-a", archived_at=None)
    repository = FakeWorkspaceRepository(workspace)

    result = await require_existing_workspace(
        workspace_id="tenant-a",
        repository=repository,
    )

    assert result is workspace
    assert repository.get_calls == ["tenant-a"]


@pytest.mark.asyncio
async def test_require_existing_workspace_rejects_missing_workspace() -> None:
    repository = FakeWorkspaceRepository(None)

    with pytest.raises(HTTPException) as exc_info:
        await require_existing_workspace(
            workspace_id="tenant-a",
            repository=repository,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "workspace not found"


@pytest.mark.asyncio
async def test_require_active_workspace_accepts_unarchived_workspace() -> None:
    workspace = SimpleNamespace(id="tenant-a", archived_at=None)
    repository = FakeWorkspaceRepository(workspace)

    result = await require_active_workspace(
        workspace_id="tenant-a",
        repository=repository,
    )

    assert result is workspace


@pytest.mark.asyncio
async def test_require_active_workspace_rejects_archived_workspace() -> None:
    repository = FakeWorkspaceRepository(
        SimpleNamespace(
            id="tenant-a",
            archived_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_active_workspace(
            workspace_id="tenant-a",
            repository=repository,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "workspace archived"
