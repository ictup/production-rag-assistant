import uuid
from datetime import UTC, datetime
from hashlib import sha256

from fastapi.testclient import TestClient

from backend.app.api import routes_workspaces
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import Workspace, WorkspaceAuditLog
from backend.app.db.repositories import (
    ArchiveWorkspaceInput,
    BulkWorkspaceOperationResult,
    CreateWorkspaceAuditLogInput,
    CreateWorkspaceInput,
    CreateWorkspaceResult,
    UpdateWorkspaceInput,
    WorkspaceAuditLogListResult,
    WorkspaceListResult,
)
from backend.app.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class FakeWorkspaceRepository:
    def __init__(
        self,
        *,
        create_result: CreateWorkspaceResult | None = None,
        list_result: WorkspaceListResult | None = None,
        audit_list_result: WorkspaceAuditLogListResult | None = None,
        detail_workspace: Workspace | None = None,
        bulk_missing_ids: list[str] | None = None,
    ) -> None:
        self.create_result = create_result or CreateWorkspaceResult(
            workspace=make_workspace_model(),
            created=True,
        )
        self.list_result = list_result or WorkspaceListResult(
            total=0,
            workspaces=[],
        )
        self.audit_list_result = audit_list_result or WorkspaceAuditLogListResult(
            total=0,
            audit_logs=[],
        )
        self.detail_workspace = detail_workspace
        self.bulk_missing_ids = bulk_missing_ids or []
        self.create_calls: list[tuple[CreateWorkspaceInput, bool]] = []
        self.update_calls: list[tuple[UpdateWorkspaceInput, bool]] = []
        self.archive_calls: list[tuple[ArchiveWorkspaceInput, bool]] = []
        self.bulk_archive_calls: list[tuple[list[ArchiveWorkspaceInput], bool]] = []
        self.restore_calls: list[tuple[str, bool]] = []
        self.bulk_restore_calls: list[tuple[list[str], bool]] = []
        self.audit_calls: list[tuple[CreateWorkspaceAuditLogInput, bool]] = []
        self.list_calls: list[
            tuple[frozenset[str] | None, int, int, str | None, bool | None]
        ] = []
        self.audit_list_calls: list[
            tuple[
                int,
                int,
                str | None,
                str | None,
                str | None,
                datetime | None,
                datetime | None,
                frozenset[str] | None,
            ]
        ] = []
        self.detail_calls: list[str] = []

    async def create_workspace(
        self,
        workspace_input: CreateWorkspaceInput,
        *,
        commit: bool = False,
    ) -> CreateWorkspaceResult:
        self.create_calls.append((workspace_input, commit))
        return self.create_result

    async def list_workspaces(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        workspace_ids: frozenset[str] | None = None,
        search: str | None = None,
        archived: bool | None = None,
    ) -> WorkspaceListResult:
        self.list_calls.append((workspace_ids, limit, offset, search, archived))
        return self.list_result

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
        self.audit_list_calls.append(
            (
                limit,
                offset,
                action,
                workspace_id,
                request_id,
                created_from,
                created_to,
                allowed_workspaces,
            )
        )
        return self.audit_list_result

    async def get_workspace(self, *, workspace_id: str) -> Workspace | None:
        self.detail_calls.append(workspace_id)
        return self.detail_workspace

    async def update_workspace(
        self,
        workspace_input: UpdateWorkspaceInput,
        *,
        commit: bool = False,
    ) -> Workspace | None:
        self.update_calls.append((workspace_input, commit))
        if self.detail_workspace is None:
            return None
        if workspace_input.update_name:
            self.detail_workspace.name = workspace_input.name
        if workspace_input.update_description:
            self.detail_workspace.description = workspace_input.description
        if workspace_input.update_metadata:
            self.detail_workspace.metadata_ = dict(workspace_input.metadata or {})
        return self.detail_workspace

    async def archive_workspace(
        self,
        workspace_input: ArchiveWorkspaceInput,
        *,
        commit: bool = False,
    ) -> Workspace | None:
        self.archive_calls.append((workspace_input, commit))
        if self.detail_workspace is None:
            return None
        self.detail_workspace.archived_at = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
        self.detail_workspace.archived_reason = workspace_input.reason
        return self.detail_workspace

    async def archive_workspaces(
        self,
        workspace_inputs: list[ArchiveWorkspaceInput],
        *,
        commit: bool = False,
    ) -> BulkWorkspaceOperationResult:
        self.bulk_archive_calls.append((list(workspace_inputs), commit))
        if self.bulk_missing_ids:
            return BulkWorkspaceOperationResult(
                workspaces=[],
                missing_ids=self.bulk_missing_ids,
            )
        workspaces = []
        for workspace_input in workspace_inputs:
            workspace = make_workspace_model(workspace_id=workspace_input.id)
            workspace.archived_at = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
            workspace.archived_reason = workspace_input.reason
            workspaces.append(workspace)
        return BulkWorkspaceOperationResult(workspaces=workspaces, missing_ids=[])

    async def restore_workspace(
        self,
        *,
        workspace_id: str,
        commit: bool = False,
    ) -> Workspace | None:
        self.restore_calls.append((workspace_id, commit))
        if self.detail_workspace is None:
            return None
        self.detail_workspace.archived_at = None
        self.detail_workspace.archived_reason = None
        return self.detail_workspace

    async def restore_workspaces(
        self,
        *,
        workspace_ids: list[str],
        commit: bool = False,
    ) -> BulkWorkspaceOperationResult:
        self.bulk_restore_calls.append((list(workspace_ids), commit))
        if self.bulk_missing_ids:
            return BulkWorkspaceOperationResult(
                workspaces=[],
                missing_ids=self.bulk_missing_ids,
            )
        return BulkWorkspaceOperationResult(
            workspaces=[
                make_workspace_model(workspace_id=workspace_id)
                for workspace_id in workspace_ids
            ],
            missing_ids=[],
        )

    async def create_workspace_audit_log(
        self,
        audit_input: CreateWorkspaceAuditLogInput,
        *,
        commit: bool = False,
    ) -> None:
        self.audit_calls.append((audit_input, commit))


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
        metadata_={"mode": "explicit_ids", "reason": "Cleanup"},
        created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
    )


def expected_actor_hash(token: str = "dev-key") -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def build_client(
    fake_repository: FakeWorkspaceRepository,
    settings: Settings | None = None,
) -> TestClient:
    settings = settings or Settings(api_keys="dev-key")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_workspaces.get_workspace_repository] = (
        lambda: fake_repository
    )
    return TestClient(app)


def assert_workspace_audit_call(
    fake_repository: FakeWorkspaceRepository,
    *,
    action: str,
    workspace_ids: list[str],
    metadata: dict,
    token: str = "dev-key",
) -> None:
    audit_input, commit = fake_repository.audit_calls[-1]

    assert commit is True
    assert audit_input.request_id
    assert audit_input.actor_hash == expected_actor_hash(token)
    assert audit_input.action == action
    assert list(audit_input.workspace_ids) == workspace_ids
    assert audit_input.metadata == metadata


def test_create_workspace_route_creates_workspace() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces",
        headers=AUTH_HEADERS,
        json={
            "id": " tenant-a ",
            "name": " Tenant A ",
            "description": " GPU systems team ",
            "metadata": {"tier": "internal"},
        },
    )

    assert response.status_code == 201
    workspace_input, commit = fake_repository.create_calls[0]
    assert workspace_input.id == "tenant-a"
    assert workspace_input.name == "Tenant A"
    assert workspace_input.description == "GPU systems team"
    assert workspace_input.metadata == {"tier": "internal"}
    assert commit is True
    assert response.json()["created"] is True
    assert response.json()["workspace"]["id"] == "tenant-a"
    assert response.json()["workspace"]["archived_at"] is None
    assert response.json()["workspace"]["archived_reason"] is None


def test_create_workspace_route_returns_200_for_existing_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(
        create_result=CreateWorkspaceResult(
            workspace=make_workspace_model(),
            created=False,
        )
    )
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces",
        headers=AUTH_HEADERS,
        json={"id": "tenant-a"},
    )

    assert response.status_code == 200
    assert response.json()["created"] is False


def test_create_workspace_route_rejects_forbidden_workspace() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.post(
        "/workspaces",
        headers={"Authorization": "Bearer tenant-key"},
        json={"id": "tenant-b"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_repository.create_calls == []


def test_list_workspaces_route_returns_paginated_workspaces() -> None:
    fake_repository = FakeWorkspaceRepository(
        list_result=WorkspaceListResult(total=1, workspaces=[make_workspace_model()])
    )
    client = build_client(fake_repository)

    response = client.get(
        "/workspaces",
        headers=AUTH_HEADERS,
        params={"limit": 10, "offset": 5},
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [(None, 10, 5, None, None)]
    body = response.json()
    assert body["total"] == 1
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["workspaces"][0]["id"] == "tenant-a"


def test_list_workspaces_route_forwards_search_query() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.get(
        "/workspaces",
        headers=AUTH_HEADERS,
        params={"q": " Tenant "},
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [(None, 20, 0, " Tenant ", None)]


def test_list_workspaces_route_forwards_status_filter() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    active_response = client.get(
        "/workspaces",
        headers=AUTH_HEADERS,
        params={"status": "active"},
    )
    archived_response = client.get(
        "/workspaces",
        headers=AUTH_HEADERS,
        params={"status": "archived"},
    )

    assert active_response.status_code == 200
    assert archived_response.status_code == 200
    assert fake_repository.list_calls == [
        (None, 20, 0, None, False),
        (None, 20, 0, None, True),
    ]


def test_list_workspaces_route_rejects_invalid_status_filter() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.get(
        "/workspaces",
        headers=AUTH_HEADERS,
        params={"status": "deleted"},
    )

    assert response.status_code == 422
    assert fake_repository.list_calls == []


def test_list_workspaces_route_filters_to_principal_allowed_workspaces() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a|tenant-b",
        ),
    )

    response = client.get(
        "/workspaces",
        headers={"Authorization": "Bearer tenant-key"},
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [
        (frozenset({"tenant-a", "tenant-b"}), 20, 0, None, None)
    ]


def test_list_workspace_audit_logs_route_returns_filtered_logs() -> None:
    audit_log = make_workspace_audit_log_model()
    fake_repository = FakeWorkspaceRepository(
        audit_list_result=WorkspaceAuditLogListResult(
            total=1,
            audit_logs=[audit_log],
        )
    )
    client = build_client(fake_repository)

    response = client.get(
        "/workspaces/audit-logs",
        headers=AUTH_HEADERS,
        params={
            "limit": 10,
            "offset": 5,
            "action": "archive",
            "workspace_id": "tenant-a",
            "request_id": "request-1",
            "created_from": "2026-05-20T07:00:00Z",
            "created_to": "2026-05-20T09:00:00Z",
        },
    )

    assert response.status_code == 200
    created_from = datetime(2026, 5, 20, 7, 0, tzinfo=UTC)
    created_to = datetime(2026, 5, 20, 9, 0, tzinfo=UTC)
    assert fake_repository.audit_list_calls == [
        (10, 5, "archive", "tenant-a", "request-1", created_from, created_to, None)
    ]
    body = response.json()
    assert body["total"] == 1
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["audit_logs"] == [
        {
            "id": "44444444-4444-4444-4444-444444444444",
            "request_id": "request-1",
            "actor_hash": "a" * 64,
            "action": "archive",
            "workspace_ids": ["tenant-a", "tenant-b"],
            "workspace_count": 2,
            "metadata": {"mode": "explicit_ids", "reason": "Cleanup"},
            "created_at": "2026-05-20T08:00:00Z",
        }
    ]


def test_list_workspace_audit_logs_route_filters_to_allowed_workspaces() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a|tenant-b",
        ),
    )

    response = client.get(
        "/workspaces/audit-logs",
        headers={"Authorization": "Bearer tenant-key"},
    )

    assert response.status_code == 200
    assert fake_repository.audit_list_calls == [
        (
            20,
            0,
            None,
            None,
            None,
            None,
            None,
            frozenset({"tenant-a", "tenant-b"}),
        )
    ]


def test_list_workspace_audit_logs_route_rejects_forbidden_workspace() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.get(
        "/workspaces/audit-logs",
        headers={"Authorization": "Bearer tenant-key"},
        params={"workspace_id": "tenant-b"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_repository.audit_list_calls == []


def test_list_workspace_audit_logs_route_rejects_invalid_time_range() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.get(
        "/workspaces/audit-logs",
        headers=AUTH_HEADERS,
        params={
            "created_from": "2026-05-20T09:00:00Z",
            "created_to": "2026-05-20T07:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "created_to must be greater than or equal to created_from"
    }
    assert fake_repository.audit_list_calls == []


def test_preview_bulk_workspaces_route_returns_matching_count_and_sample() -> None:
    fake_repository = FakeWorkspaceRepository(
        list_result=WorkspaceListResult(
            total=3,
            workspaces=[
                make_workspace_model(workspace_id="tenant-a"),
                make_workspace_model(workspace_id="tenant-b"),
            ],
        )
    )
    client = build_client(fake_repository)

    response = client.get(
        "/workspaces/bulk/preview",
        headers=AUTH_HEADERS,
        params={
            "q": " Tenant ",
            "status": "active",
            "sample_limit": 2,
        },
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [(None, 2, 0, " Tenant ", False)]
    body = response.json()
    assert body["total"] == 3
    assert body["sample_count"] == 2
    assert body["sample_limit"] == 2
    assert body["status"] == "active"
    assert body["q"] == " Tenant "
    assert [workspace["id"] for workspace in body["workspaces"]] == [
        "tenant-a",
        "tenant-b",
    ]


def test_preview_bulk_workspaces_route_filters_to_allowed_workspaces() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a|tenant-b",
        ),
    )

    response = client.get(
        "/workspaces/bulk/preview",
        headers={"Authorization": "Bearer tenant-key"},
        params={"status": "archived"},
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [
        (frozenset({"tenant-a", "tenant-b"}), 20, 0, None, True)
    ]


def test_archive_matching_workspaces_route_archives_current_query() -> None:
    fake_repository = FakeWorkspaceRepository(
        list_result=WorkspaceListResult(
            total=2,
            workspaces=[
                make_workspace_model(workspace_id="tenant-a"),
                make_workspace_model(workspace_id="tenant-b"),
            ],
        )
    )
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/archive-matching",
        headers=AUTH_HEADERS,
        json={
            "q": " Tenant ",
            "status": "active",
            "expected_total": 2,
            "confirm": True,
            "reason": " Cleanup ",
        },
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [(None, 2, 0, "Tenant", False)]
    workspace_inputs, commit = fake_repository.bulk_archive_calls[0]
    assert [workspace_input.id for workspace_input in workspace_inputs] == [
        "tenant-a",
        "tenant-b",
    ]
    assert [workspace_input.reason for workspace_input in workspace_inputs] == [
        "Cleanup",
        "Cleanup",
    ]
    assert commit is False
    assert_workspace_audit_call(
        fake_repository,
        action="archive_matching",
        workspace_ids=["tenant-a", "tenant-b"],
        metadata={
            "mode": "matching_query",
            "q": "Tenant",
            "status": "active",
            "expected_total": 2,
            "reason": "Cleanup",
        },
    )
    body = response.json()
    assert body["action"] == "archive_matching"
    assert body["requested_count"] == 2
    assert body["updated_count"] == 2


def test_archive_matching_workspaces_route_requires_confirmation() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/archive-matching",
        headers=AUTH_HEADERS,
        json={
            "status": "active",
            "expected_total": 1,
            "confirm": False,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "bulk matching operation confirmation required"
    }
    assert fake_repository.list_calls == []
    assert fake_repository.bulk_archive_calls == []
    assert fake_repository.audit_calls == []


def test_archive_matching_workspaces_route_rejects_changed_total() -> None:
    fake_repository = FakeWorkspaceRepository(
        list_result=WorkspaceListResult(
            total=3,
            workspaces=[
                make_workspace_model(workspace_id="tenant-a"),
                make_workspace_model(workspace_id="tenant-b"),
            ],
        )
    )
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/archive-matching",
        headers=AUTH_HEADERS,
        json={
            "status": "active",
            "expected_total": 2,
            "confirm": True,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "message": "bulk preview total changed",
            "expected_total": 2,
            "current_total": 3,
        }
    }
    assert fake_repository.list_calls == [(None, 2, 0, None, False)]
    assert fake_repository.bulk_archive_calls == []
    assert fake_repository.audit_calls == []


def test_archive_matching_workspaces_route_allows_zero_matches() -> None:
    fake_repository = FakeWorkspaceRepository(
        list_result=WorkspaceListResult(total=0, workspaces=[])
    )
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/archive-matching",
        headers=AUTH_HEADERS,
        json={
            "q": "missing",
            "status": "active",
            "expected_total": 0,
            "confirm": True,
        },
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [(None, 1, 0, "missing", False)]
    assert fake_repository.bulk_archive_calls == []
    assert fake_repository.audit_calls == []
    assert response.json() == {
        "action": "archive_matching",
        "requested_count": 0,
        "updated_count": 0,
        "workspaces": [],
    }


def test_restore_matching_workspaces_route_restores_current_query() -> None:
    fake_repository = FakeWorkspaceRepository(
        list_result=WorkspaceListResult(
            total=2,
            workspaces=[
                make_workspace_model(workspace_id="tenant-a"),
                make_workspace_model(workspace_id="tenant-b"),
            ],
        )
    )
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/restore-matching",
        headers=AUTH_HEADERS,
        json={
            "status": "archived",
            "expected_total": 2,
            "confirm": True,
        },
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [(None, 2, 0, None, True)]
    workspace_ids, commit = fake_repository.bulk_restore_calls[0]
    assert workspace_ids == ["tenant-a", "tenant-b"]
    assert commit is False
    assert_workspace_audit_call(
        fake_repository,
        action="restore_matching",
        workspace_ids=["tenant-a", "tenant-b"],
        metadata={
            "mode": "matching_query",
            "q": None,
            "status": "archived",
            "expected_total": 2,
        },
    )
    body = response.json()
    assert body["action"] == "restore_matching"
    assert body["requested_count"] == 2
    assert body["updated_count"] == 2


def test_restore_matching_workspaces_route_filters_to_allowed_workspaces() -> None:
    fake_repository = FakeWorkspaceRepository(
        list_result=WorkspaceListResult(
            total=1,
            workspaces=[make_workspace_model(workspace_id="tenant-a")],
        )
    )
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.post(
        "/workspaces/bulk/restore-matching",
        headers={"Authorization": "Bearer tenant-key"},
        json={
            "status": "archived",
            "expected_total": 1,
            "confirm": True,
        },
    )

    assert response.status_code == 200
    assert fake_repository.list_calls == [
        (frozenset({"tenant-a"}), 1, 0, None, True)
    ]
    assert fake_repository.bulk_restore_calls[0][0] == ["tenant-a"]
    assert_workspace_audit_call(
        fake_repository,
        action="restore_matching",
        workspace_ids=["tenant-a"],
        metadata={
            "mode": "matching_query",
            "q": None,
            "status": "archived",
            "expected_total": 1,
        },
        token="tenant-key",
    )


def test_get_workspace_route_returns_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(fake_repository)

    response = client.get("/workspaces/tenant-a", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert fake_repository.detail_calls == ["tenant-a"]
    assert response.json()["workspace"]["id"] == "tenant-a"
    assert response.json()["workspace"]["metadata"] == {"tier": "internal"}


def test_get_workspace_route_returns_404_for_missing_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=None)
    client = build_client(fake_repository)

    response = client.get("/workspaces/tenant-a", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_repository.detail_calls == ["tenant-a"]


def test_get_workspace_route_rejects_forbidden_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.get(
        "/workspaces/tenant-b",
        headers={"Authorization": "Bearer tenant-key"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_repository.detail_calls == []


def test_update_workspace_route_updates_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(fake_repository)

    response = client.patch(
        "/workspaces/tenant-a",
        headers=AUTH_HEADERS,
        json={
            "name": " Updated Tenant ",
            "description": " Updated description ",
            "metadata": {"tier": "external"},
        },
    )

    assert response.status_code == 200
    workspace_input, commit = fake_repository.update_calls[0]
    assert workspace_input.id == "tenant-a"
    assert workspace_input.name == "Updated Tenant"
    assert workspace_input.description == "Updated description"
    assert workspace_input.metadata == {"tier": "external"}
    assert workspace_input.update_name is True
    assert workspace_input.update_description is True
    assert workspace_input.update_metadata is True
    assert commit is True
    body = response.json()
    assert body["workspace"]["name"] == "Updated Tenant"
    assert body["workspace"]["metadata"] == {"tier": "external"}


def test_update_workspace_route_can_clear_optional_fields() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(fake_repository)

    response = client.patch(
        "/workspaces/tenant-a",
        headers=AUTH_HEADERS,
        json={
            "name": None,
            "description": None,
            "metadata": None,
        },
    )

    assert response.status_code == 200
    workspace_input, _ = fake_repository.update_calls[0]
    assert workspace_input.update_name is True
    assert workspace_input.update_description is True
    assert workspace_input.update_metadata is True
    assert response.json()["workspace"]["name"] is None
    assert response.json()["workspace"]["description"] is None
    assert response.json()["workspace"]["metadata"] == {}


def test_update_workspace_route_returns_404_for_missing_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=None)
    client = build_client(fake_repository)

    response = client.patch(
        "/workspaces/tenant-a",
        headers=AUTH_HEADERS,
        json={"name": "Updated Tenant"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_repository.update_calls[0][0].id == "tenant-a"


def test_update_workspace_route_rejects_forbidden_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.patch(
        "/workspaces/tenant-b",
        headers={"Authorization": "Bearer tenant-key"},
        json={"name": "Updated Tenant"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_repository.update_calls == []


def test_archive_workspace_route_archives_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/tenant-a/archive",
        headers=AUTH_HEADERS,
        json={"reason": " Retired tenant "},
    )

    assert response.status_code == 200
    workspace_input, commit = fake_repository.archive_calls[0]
    assert workspace_input.id == "tenant-a"
    assert workspace_input.reason == "Retired tenant"
    assert commit is False
    assert_workspace_audit_call(
        fake_repository,
        action="archive",
        workspace_ids=["tenant-a"],
        metadata={
            "mode": "single_workspace",
            "reason": "Retired tenant",
        },
    )
    body = response.json()
    assert body["workspace"]["archived_at"] == "2026-05-20T08:00:00Z"
    assert body["workspace"]["archived_reason"] == "Retired tenant"


def test_archive_workspace_route_accepts_empty_body() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/tenant-a/archive",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    workspace_input, _ = fake_repository.archive_calls[0]
    assert workspace_input.reason is None
    assert_workspace_audit_call(
        fake_repository,
        action="archive",
        workspace_ids=["tenant-a"],
        metadata={
            "mode": "single_workspace",
            "reason": None,
        },
    )


def test_archive_workspace_route_returns_404_for_missing_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=None)
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/tenant-a/archive",
        headers=AUTH_HEADERS,
        json={"reason": "Retired tenant"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_repository.archive_calls[0][0].id == "tenant-a"
    assert fake_repository.audit_calls == []


def test_archive_workspace_route_rejects_forbidden_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=make_workspace_model())
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.post(
        "/workspaces/tenant-b/archive",
        headers={"Authorization": "Bearer tenant-key"},
        json={"reason": "Retired tenant"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_repository.archive_calls == []
    assert fake_repository.audit_calls == []


def test_bulk_archive_workspaces_route_archives_workspaces() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/archive",
        headers=AUTH_HEADERS,
        json={
            "ids": [" tenant-a ", "tenant-b", "tenant-a"],
            "reason": " Cleanup ",
        },
    )

    assert response.status_code == 200
    workspace_inputs, commit = fake_repository.bulk_archive_calls[0]
    assert [workspace_input.id for workspace_input in workspace_inputs] == [
        "tenant-a",
        "tenant-b",
    ]
    assert [workspace_input.reason for workspace_input in workspace_inputs] == [
        "Cleanup",
        "Cleanup",
    ]
    assert commit is False
    assert_workspace_audit_call(
        fake_repository,
        action="archive",
        workspace_ids=["tenant-a", "tenant-b"],
        metadata={
            "mode": "explicit_ids",
            "requested_count": 2,
            "reason": "Cleanup",
        },
    )
    body = response.json()
    assert body["action"] == "archive"
    assert body["requested_count"] == 2
    assert body["updated_count"] == 2
    assert [workspace["id"] for workspace in body["workspaces"]] == [
        "tenant-a",
        "tenant-b",
    ]


def test_bulk_archive_workspaces_route_rejects_forbidden_workspace() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(
        fake_repository,
        settings=Settings(
            api_keys="tenant-key",
            api_key_workspace_access="tenant-key=tenant-a",
        ),
    )

    response = client.post(
        "/workspaces/bulk/archive",
        headers={"Authorization": "Bearer tenant-key"},
        json={"ids": ["tenant-a", "tenant-b"]},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_repository.bulk_archive_calls == []
    assert fake_repository.audit_calls == []


def test_bulk_archive_workspaces_route_returns_missing_workspace_ids() -> None:
    fake_repository = FakeWorkspaceRepository(bulk_missing_ids=["tenant-missing"])
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/archive",
        headers=AUTH_HEADERS,
        json={"ids": ["tenant-a", "tenant-missing"]},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "message": "workspace not found",
            "workspace_ids": ["tenant-missing"],
        }
    }
    assert fake_repository.bulk_archive_calls
    assert fake_repository.audit_calls == []


def test_restore_workspace_route_restores_workspace() -> None:
    workspace = make_workspace_model()
    workspace.archived_at = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
    workspace.archived_reason = "Retired tenant"
    fake_repository = FakeWorkspaceRepository(detail_workspace=workspace)
    client = build_client(fake_repository)

    response = client.post("/workspaces/tenant-a/restore", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert fake_repository.restore_calls == [("tenant-a", False)]
    assert_workspace_audit_call(
        fake_repository,
        action="restore",
        workspace_ids=["tenant-a"],
        metadata={"mode": "single_workspace"},
    )
    assert response.json()["workspace"]["archived_at"] is None
    assert response.json()["workspace"]["archived_reason"] is None


def test_restore_workspace_route_returns_404_for_missing_workspace() -> None:
    fake_repository = FakeWorkspaceRepository(detail_workspace=None)
    client = build_client(fake_repository)

    response = client.post("/workspaces/tenant-a/restore", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_repository.restore_calls == [("tenant-a", False)]
    assert fake_repository.audit_calls == []


def test_bulk_restore_workspaces_route_restores_workspaces() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/restore",
        headers=AUTH_HEADERS,
        json={"ids": [" tenant-a ", "tenant-b", "tenant-a"]},
    )

    assert response.status_code == 200
    workspace_ids, commit = fake_repository.bulk_restore_calls[0]
    assert workspace_ids == ["tenant-a", "tenant-b"]
    assert commit is False
    assert_workspace_audit_call(
        fake_repository,
        action="restore",
        workspace_ids=["tenant-a", "tenant-b"],
        metadata={
            "mode": "explicit_ids",
            "requested_count": 2,
        },
    )
    body = response.json()
    assert body["action"] == "restore"
    assert body["requested_count"] == 2
    assert body["updated_count"] == 2
    assert [workspace["id"] for workspace in body["workspaces"]] == [
        "tenant-a",
        "tenant-b",
    ]
    assert body["workspaces"][0]["archived_at"] is None


def test_bulk_restore_workspaces_route_returns_missing_workspace_ids() -> None:
    fake_repository = FakeWorkspaceRepository(bulk_missing_ids=["tenant-missing"])
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/restore",
        headers=AUTH_HEADERS,
        json={"ids": ["tenant-a", "tenant-missing"]},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "message": "workspace not found",
            "workspace_ids": ["tenant-missing"],
        }
    }
    assert fake_repository.bulk_restore_calls
    assert fake_repository.audit_calls == []


def test_bulk_workspace_routes_reject_empty_ids() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.post(
        "/workspaces/bulk/archive",
        headers=AUTH_HEADERS,
        json={"ids": []},
    )

    assert response.status_code == 422
    assert fake_repository.bulk_archive_calls == []
    assert fake_repository.audit_calls == []


def test_workspaces_routes_require_api_key() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.get("/workspaces")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_repository.list_calls == []


def test_openapi_exposes_workspace_routes() -> None:
    fake_repository = FakeWorkspaceRepository()
    client = build_client(fake_repository)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/workspaces" in paths
    assert "/workspaces/audit-logs" in paths
    assert "/workspaces/{workspace_id}" in paths
    assert "patch" in paths["/workspaces/{workspace_id}"]
    assert "/workspaces/bulk/preview" in paths
    assert "/workspaces/bulk/archive-matching" in paths
    assert "/workspaces/bulk/restore-matching" in paths
    assert "/workspaces/bulk/archive" in paths
    assert "/workspaces/bulk/restore" in paths
    assert "/workspaces/{workspace_id}/archive" in paths
    assert "/workspaces/{workspace_id}/restore" in paths
