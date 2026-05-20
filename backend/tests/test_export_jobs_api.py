import uuid
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api import routes_exports
from backend.app.api.workspace_validation import get_workspace_repository
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import ExportJob, Workspace
from backend.app.db.repositories import (
    CreateExportJobInput,
    ExportJobListResult,
)
from backend.app.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer dev-key"}


class FakeExportJobRepository:
    def __init__(
        self,
        *,
        created_job: ExportJob | None = None,
        list_result: ExportJobListResult | None = None,
        detail_job: ExportJob | None = None,
    ) -> None:
        self.created_job = created_job
        self.list_result = list_result or ExportJobListResult(total=0, jobs=[])
        self.detail_job = detail_job
        self.create_calls: list[tuple[CreateExportJobInput, bool]] = []
        self.list_calls: list[tuple[str, int, int, str | None, str | None]] = []
        self.detail_calls: list[tuple[uuid.UUID, str | None]] = []
        self.retry_calls: list[tuple[uuid.UUID, str | None, bool]] = []

    async def create_export_job(
        self,
        export_input: CreateExportJobInput,
        *,
        commit: bool = False,
    ) -> ExportJob:
        self.create_calls.append((export_input, commit))
        return self.created_job or make_export_job_model(
            workspace_id=export_input.workspace_id,
            request_id=export_input.request_id,
            actor_hash=export_input.actor_hash,
            export_type=export_input.export_type,
            export_format=export_input.format,
            filters=dict(export_input.filters or {}),
        )

    async def list_export_jobs(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        export_type: str | None = None,
    ) -> ExportJobListResult:
        self.list_calls.append((workspace_id, limit, offset, status, export_type))
        return self.list_result

    async def get_export_job(
        self,
        *,
        job_id: uuid.UUID,
        workspace_id: str | None = None,
    ) -> ExportJob | None:
        self.detail_calls.append((job_id, workspace_id))
        return self.detail_job

    async def retry_failed_export_job(
        self,
        *,
        job_id: uuid.UUID,
        workspace_id: str | None = None,
        commit: bool = False,
    ) -> ExportJob | None:
        self.retry_calls.append((job_id, workspace_id, commit))
        if self.detail_job is None:
            return None
        if self.detail_job.status != "failed":
            raise ValueError("export job must be failed to retry")
        self.detail_job.status = "pending"
        self.detail_job.result_uri = None
        self.detail_job.result_media_type = None
        self.detail_job.result_size_bytes = None
        self.detail_job.error_message = None
        self.detail_job.started_at = None
        self.detail_job.completed_at = None
        return self.detail_job


class FakeWorkspaceRepository:
    def __init__(self, workspace: Workspace | None = None) -> None:
        self.workspace = workspace or make_workspace_model()
        self.get_calls: list[str] = []

    async def get_workspace(self, *, workspace_id: str) -> Workspace | None:
        self.get_calls.append(workspace_id)
        return self.workspace


def make_workspace_model(
    *,
    workspace_id: str = "tenant-a",
    archived: bool = False,
) -> Workspace:
    return Workspace(
        id=workspace_id,
        name="Tenant A",
        description="GPU systems team",
        metadata_={"tier": "internal"},
        created_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
        archived_at=(
            datetime(2026, 5, 20, 8, 0, tzinfo=UTC) if archived else None
        ),
        archived_reason="Audit recovery" if archived else None,
    )


def make_export_job_model(
    *,
    workspace_id: str = "tenant-a",
    request_id: str = "request-1",
    actor_hash: str | None = None,
    export_type: str = "chat_logs",
    export_format: str = "jsonl",
    filters: dict | None = None,
    status: str = "pending",
) -> ExportJob:
    return ExportJob(
        id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        workspace_id=workspace_id,
        request_id=request_id,
        actor_hash=actor_hash or expected_actor_hash(),
        export_type=export_type,
        format=export_format,
        status=status,
        filters_=filters or {"limit": 1000, "offset": 0, "refusal_only": False},
        result_uri=None,
        result_media_type=None,
        result_size_bytes=None,
        error_message=None,
        created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        started_at=None,
        completed_at=None,
    )


def expected_actor_hash(token: str = "dev-key") -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def build_client(
    fake_export_job_repository: FakeExportJobRepository,
    fake_workspace_repository: FakeWorkspaceRepository | None = None,
    settings: Settings | None = None,
) -> TestClient:
    settings = settings or Settings(api_keys="dev-key")
    fake_workspace_repository = fake_workspace_repository or FakeWorkspaceRepository()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_exports.get_export_job_repository] = (
        lambda: fake_export_job_repository
    )
    app.dependency_overrides[get_workspace_repository] = (
        lambda: fake_workspace_repository
    )
    return TestClient(app)


def test_openapi_exposes_export_job_routes() -> None:
    client = build_client(FakeExportJobRepository())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/exports/jobs" in paths
    assert "/exports/jobs/{job_id}" in paths
    assert "/exports/jobs/{job_id}/retry" in paths
    assert "/exports/jobs/{job_id}/download" in paths


def test_create_export_job_creates_pending_job_for_workspace() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    fake_workspace_repository = FakeWorkspaceRepository(make_workspace_model())
    client = build_client(fake_export_job_repository, fake_workspace_repository)

    response = client.post(
        "/exports/jobs",
        headers={
            **AUTH_HEADERS,
            "X-Workspace-ID": " tenant-a ",
            "X-Request-ID": " request-1 ",
        },
        json={
            "export_type": "chat_logs",
            "format": "csv",
            "filters": {
                "limit": 25,
                "offset": 50,
                "request_id": "chat-request-1",
                "refusal_only": True,
                "citation_valid": False,
            },
        },
    )

    assert response.status_code == 202
    assert fake_workspace_repository.get_calls == ["tenant-a"]
    export_input, commit = fake_export_job_repository.create_calls[0]
    assert commit is True
    assert export_input.request_id == "request-1"
    assert export_input.actor_hash == expected_actor_hash()
    assert export_input.workspace_id == "tenant-a"
    assert export_input.export_type == "chat_logs"
    assert export_input.format == "csv"
    assert export_input.filters == {
        "limit": 25,
        "offset": 50,
        "request_id": "chat-request-1",
        "refusal_only": True,
        "citation_valid": False,
    }
    body = response.json()["job"]
    assert body["workspace_id"] == "tenant-a"
    assert body["request_id"] == "request-1"
    assert body["actor_hash"] == expected_actor_hash()
    assert body["format"] == "csv"
    assert body["status"] == "pending"


def test_create_export_job_defaults_to_public_workspace_and_jsonl() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    fake_workspace_repository = FakeWorkspaceRepository(
        make_workspace_model(workspace_id="public")
    )
    client = build_client(fake_export_job_repository, fake_workspace_repository)

    response = client.post(
        "/exports/jobs",
        headers=AUTH_HEADERS,
        json={},
    )

    assert response.status_code == 202
    assert fake_workspace_repository.get_calls == ["public"]
    export_input, _ = fake_export_job_repository.create_calls[0]
    assert export_input.workspace_id == "public"
    assert export_input.export_type == "chat_logs"
    assert export_input.format == "jsonl"
    assert export_input.filters == {
        "limit": 1000,
        "offset": 0,
        "refusal_only": False,
    }


def test_create_export_job_allows_archived_workspace() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    fake_workspace_repository = FakeWorkspaceRepository(
        make_workspace_model(archived=True)
    )
    client = build_client(fake_export_job_repository, fake_workspace_repository)

    response = client.post(
        "/exports/jobs",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
        json={"export_type": "chat_logs"},
    )

    assert response.status_code == 202
    assert fake_export_job_repository.create_calls


def test_create_export_job_returns_404_for_missing_workspace() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    fake_workspace_repository = FakeWorkspaceRepository(workspace=None)
    fake_workspace_repository.workspace = None
    client = build_client(fake_export_job_repository, fake_workspace_repository)

    response = client.post(
        "/exports/jobs",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
        json={"export_type": "chat_logs"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found"}
    assert fake_export_job_repository.create_calls == []


def test_create_export_job_rejects_workspace_access_denied() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    fake_workspace_repository = FakeWorkspaceRepository(make_workspace_model())
    client = build_client(
        fake_export_job_repository,
        fake_workspace_repository,
        Settings(api_keys="dev-key", api_key_workspace_access="dev-key=tenant-a"),
    )

    response = client.post(
        "/exports/jobs",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-b"},
        json={"export_type": "chat_logs"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_workspace_repository.get_calls == []
    assert fake_export_job_repository.create_calls == []


def test_create_export_job_rejects_invalid_format() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    client = build_client(fake_export_job_repository)

    response = client.post(
        "/exports/jobs",
        headers=AUTH_HEADERS,
        json={"export_type": "chat_logs", "format": "xml"},
    )

    assert response.status_code == 422
    assert fake_export_job_repository.create_calls == []


def test_list_export_jobs_forwards_workspace_and_filters() -> None:
    export_job = make_export_job_model(status="succeeded")
    fake_export_job_repository = FakeExportJobRepository(
        list_result=ExportJobListResult(total=7, jobs=[export_job])
    )
    client = build_client(fake_export_job_repository)

    response = client.get(
        "/exports/jobs",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
        params={
            "limit": 5,
            "offset": 10,
            "status": "succeeded",
            "export_type": "chat_logs",
        },
    )

    assert response.status_code == 200
    assert fake_export_job_repository.list_calls == [
        ("tenant-a", 5, 10, "succeeded", "chat_logs")
    ]
    body = response.json()
    assert body["total"] == 7
    assert body["count"] == 1
    assert body["limit"] == 5
    assert body["offset"] == 10
    assert body["jobs"][0]["id"] == "55555555-5555-5555-5555-555555555555"
    assert body["jobs"][0]["status"] == "succeeded"


def test_list_export_jobs_requires_api_key() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    client = build_client(fake_export_job_repository)

    response = client.get("/exports/jobs")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing api key"}
    assert fake_export_job_repository.list_calls == []


def test_list_export_jobs_rejects_invalid_status() -> None:
    fake_export_job_repository = FakeExportJobRepository()
    client = build_client(fake_export_job_repository)

    response = client.get(
        "/exports/jobs",
        headers=AUTH_HEADERS,
        params={"status": "queued"},
    )

    assert response.status_code == 422
    assert fake_export_job_repository.list_calls == []


def test_get_export_job_returns_job_for_workspace() -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    export_job = make_export_job_model()
    fake_export_job_repository = FakeExportJobRepository(detail_job=export_job)
    client = build_client(fake_export_job_repository)

    response = client.get(
        f"/exports/jobs/{job_id}",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 200
    assert fake_export_job_repository.detail_calls == [(job_id, "tenant-a")]
    body = response.json()["job"]
    assert body["id"] == str(job_id)
    assert body["workspace_id"] == "tenant-a"
    assert body["filters"] == {"limit": 1000, "offset": 0, "refusal_only": False}


def test_get_export_job_returns_404_when_not_found() -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    fake_export_job_repository = FakeExportJobRepository(detail_job=None)
    client = build_client(fake_export_job_repository)

    response = client.get(
        f"/exports/jobs/{job_id}",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "export job not found"}
    assert fake_export_job_repository.detail_calls == [(job_id, "tenant-a")]


def test_retry_export_job_resets_failed_job_to_pending_for_workspace() -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    export_job = make_export_job_model(status="failed")
    export_job.error_message = "permission denied"
    export_job.started_at = datetime(2026, 5, 20, 8, 1, tzinfo=UTC)
    export_job.completed_at = datetime(2026, 5, 20, 8, 2, tzinfo=UTC)
    fake_export_job_repository = FakeExportJobRepository(detail_job=export_job)
    client = build_client(fake_export_job_repository)

    response = client.post(
        f"/exports/jobs/{job_id}/retry",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 202
    assert fake_export_job_repository.retry_calls == [(job_id, "tenant-a", True)]
    body = response.json()["job"]
    assert body["id"] == str(job_id)
    assert body["status"] == "pending"
    assert body["error_message"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None


def test_retry_export_job_returns_404_when_not_found() -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    fake_export_job_repository = FakeExportJobRepository(detail_job=None)
    client = build_client(fake_export_job_repository)

    response = client.post(
        f"/exports/jobs/{job_id}/retry",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "export job not found"}
    assert fake_export_job_repository.retry_calls == [(job_id, "tenant-a", True)]


def test_retry_export_job_rejects_non_failed_job() -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    fake_export_job_repository = FakeExportJobRepository(
        detail_job=make_export_job_model(status="pending")
    )
    client = build_client(fake_export_job_repository)

    response = client.post(
        f"/exports/jobs/{job_id}/retry",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "export job is not failed"}
    assert fake_export_job_repository.retry_calls == [(job_id, "tenant-a", True)]


def test_retry_export_job_rejects_workspace_access_denied() -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    fake_export_job_repository = FakeExportJobRepository(
        detail_job=make_export_job_model(status="failed")
    )
    client = build_client(
        fake_export_job_repository,
        settings=Settings(
            api_keys="dev-key",
            api_key_workspace_access="dev-key=tenant-a",
        ),
    )

    response = client.post(
        f"/exports/jobs/{job_id}/retry",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-b"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "workspace access denied"}
    assert fake_export_job_repository.retry_calls == []


def test_download_export_job_returns_file_for_succeeded_job(tmp_path: Path) -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    result_path = tmp_path / "chat-logs-tenant-a.csv"
    result_path.write_text("request_id,workspace_id\nrequest-1,tenant-a\n")
    export_job = make_export_job_model(status="succeeded", export_format="csv")
    export_job.result_uri = result_path.resolve().as_uri()
    export_job.result_media_type = "text/csv; charset=utf-8"
    export_job.result_size_bytes = result_path.stat().st_size
    fake_export_job_repository = FakeExportJobRepository(detail_job=export_job)
    client = build_client(
        fake_export_job_repository,
        settings=Settings(api_keys="dev-key", export_storage_dir=str(tmp_path)),
    )

    response = client.get(
        f"/exports/jobs/{job_id}/download",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert 'filename="chat-logs-tenant-a.csv"' in response.headers[
        "content-disposition"
    ]
    assert response.text.replace("\r\n", "\n") == (
        "request_id,workspace_id\nrequest-1,tenant-a\n"
    )
    assert fake_export_job_repository.detail_calls == [(job_id, "tenant-a")]


def test_download_export_job_rejects_pending_job(tmp_path: Path) -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    fake_export_job_repository = FakeExportJobRepository(
        detail_job=make_export_job_model(status="pending")
    )
    client = build_client(
        fake_export_job_repository,
        settings=Settings(api_keys="dev-key", export_storage_dir=str(tmp_path)),
    )

    response = client.get(
        f"/exports/jobs/{job_id}/download",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "export job not ready"}


def test_download_export_job_rejects_result_outside_storage_dir(
    tmp_path: Path,
) -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    storage_dir = tmp_path / "exports"
    storage_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "chat-logs-tenant-a.jsonl"
    outside_file.write_text("{}\n")
    export_job = make_export_job_model(status="succeeded")
    export_job.result_uri = outside_file.resolve().as_uri()
    export_job.result_media_type = "application/x-ndjson; charset=utf-8"
    fake_export_job_repository = FakeExportJobRepository(detail_job=export_job)
    client = build_client(
        fake_export_job_repository,
        settings=Settings(api_keys="dev-key", export_storage_dir=str(storage_dir)),
    )

    response = client.get(
        f"/exports/jobs/{job_id}/download",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "export file not found"}


def test_download_export_job_rejects_non_file_result_uri(tmp_path: Path) -> None:
    job_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    export_job = make_export_job_model(status="succeeded")
    export_job.result_uri = "https://example.com/export.jsonl"
    export_job.result_media_type = "application/x-ndjson; charset=utf-8"
    fake_export_job_repository = FakeExportJobRepository(detail_job=export_job)
    client = build_client(
        fake_export_job_repository,
        settings=Settings(api_keys="dev-key", export_storage_dir=str(tmp_path)),
    )

    response = client.get(
        f"/exports/jobs/{job_id}/download",
        headers={**AUTH_HEADERS, "X-Workspace-ID": "tenant-a"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "export result is not a local file"}
