from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_root_redirects_to_static_app() -> None:
    client = TestClient(create_app(), follow_redirects=False)

    response = client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


def test_static_app_serves_index_html() -> None:
    client = TestClient(create_app())

    response = client.get("/app/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Production RAG Assistant" in response.text
    assert 'id="chat-form"' in response.text
    assert 'id="workspace-archive-banner"' in response.text
    assert 'id="document-form"' in response.text
    assert 'id="reindex-dry-run"' in response.text
    assert 'id="reload-admin"' in response.text
    assert 'id="admin-workspace-form"' in response.text
    assert 'id="admin-workspace-id"' in response.text
    assert 'id="create-admin-workspace"' in response.text
    assert 'id="admin-workspace-filter-all"' in response.text
    assert 'id="admin-workspace-filter-active"' in response.text
    assert 'id="admin-workspace-filter-archived"' in response.text
    assert 'id="admin-workspace-filter-summary"' in response.text
    assert 'id="admin-prev-workspaces"' in response.text
    assert 'id="admin-workspace-page-info"' in response.text
    assert 'id="admin-next-workspaces"' in response.text
    assert 'id="admin-workspace-search-form"' in response.text
    assert 'id="admin-workspace-search"' in response.text
    assert 'id="admin-search-workspaces"' in response.text
    assert 'id="admin-clear-workspace-search"' in response.text
    assert 'id="admin-workspace-edit-form"' in response.text
    assert 'id="admin-edit-workspace-metadata"' in response.text
    assert 'id="admin-archive-workspace-reason"' in response.text
    assert 'id="save-admin-workspace"' in response.text
    assert 'id="archive-admin-workspace"' in response.text
    assert 'id="restore-admin-workspace"' in response.text
    assert 'id="admin-filter-form"' in response.text
    assert 'id="admin-request-id"' in response.text
    assert 'id="export-admin-jsonl"' in response.text
    assert 'id="export-admin-csv"' in response.text
    assert 'id="admin-prev-logs"' in response.text
    assert 'id="admin-workspace-list"' in response.text
    assert 'id="admin-log-list"' in response.text


def test_static_app_serves_assets() -> None:
    client = TestClient(create_app())

    script_response = client.get("/app/app.js")
    style_response = client.get("/app/app.css")

    assert script_response.status_code == 200
    assert "const state" in script_response.text
    assert "uploadDocument" in script_response.text
    assert "reindexDocuments" in script_response.text
    assert "loadAdminOverview" in script_response.text
    assert "createWorkspaceFromAdmin" in script_response.text
    assert "updateWorkspaceFromAdmin" in script_response.text
    assert "archiveWorkspaceFromAdmin" in script_response.text
    assert "restoreWorkspaceFromAdmin" in script_response.text
    assert "workspaceLifecycleText" in script_response.text
    assert "setAdminWorkspaceFilter" in script_response.text
    assert "clearAdminWorkspaceSearch" in script_response.text
    assert "buildWorkspacesUrl" in script_response.text
    assert "filteredAdminWorkspaces" in script_response.text
    assert "renderAdminWorkspacePagination" in script_response.text
    assert "workspaceFilterEmptyMessage" in script_response.text
    assert "isCurrentWorkspaceArchived" in script_response.text
    assert "syncWorkspaceWriteGuards" in script_response.text
    assert "guardArchivedWorkspace" in script_response.text
    assert "parseMetadataJson" in script_response.text
    assert "syncWorkspaceEditForm" in script_response.text
    assert "optionalText" in script_response.text
    assert "buildChatLogsUrl" in script_response.text
    assert "buildChatLogsExportUrl" in script_response.text
    assert "exportAdminLogs" in script_response.text
    assert "/chat/logs/export?" in script_response.text
    assert "readAdminFilters" in script_response.text
    assert "refusal_only" in script_response.text
    assert "buildChatLogAuditDetails" in script_response.text
    assert "formatRefusal" in script_response.text
    assert "formatUsage" in script_response.text
    assert "formatCost" in script_response.text
    assert "/workspaces?" in script_response.text
    assert 'params.set("q", state.admin.workspaceSearch)' in script_response.text
    assert "workspaceOffset" in script_response.text
    assert "/archive" in script_response.text
    assert "/restore" in script_response.text
    assert "/chat/logs?" in script_response.text
    assert "renderMessageError" in script_response.text
    assert "providerErrorUserMessage" in script_response.text
    assert "Retry" in script_response.text
    assert style_response.status_code == 200
    assert ".chat-panel" in style_response.text
    assert ".knowledge-panel" in style_response.text
    assert ".workspace-archive-banner" in style_response.text
    assert ".admin-panel" in style_response.text
    assert ".admin-workspace-filter-actions" in style_response.text
    assert ".admin-workspace-search-form" in style_response.text
    assert ".admin-create-form" in style_response.text
    assert ".admin-edit-form" in style_response.text
    assert ".admin-workspace-actions" in style_response.text
    assert ".admin-workspace.archived" in style_response.text
    assert ".admin-filter-form" in style_response.text
    assert ".admin-export-actions" in style_response.text
    assert ".admin-pagination" in style_response.text
    assert ".admin-stat" in style_response.text
    assert ".admin-item" in style_response.text
    assert ".admin-detail" in style_response.text
    assert ".admin-detail-row" in style_response.text
    assert ".message-error" in style_response.text
    assert ".retry-button" in style_response.text
