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
    assert 'id="document-form"' in response.text
    assert 'id="reindex-dry-run"' in response.text
    assert 'id="reload-admin"' in response.text
    assert 'id="admin-filter-form"' in response.text
    assert 'id="admin-request-id"' in response.text
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
    assert "buildChatLogsUrl" in script_response.text
    assert "readAdminFilters" in script_response.text
    assert "refusal_only" in script_response.text
    assert "buildChatLogAuditDetails" in script_response.text
    assert "formatRefusal" in script_response.text
    assert "formatUsage" in script_response.text
    assert "formatCost" in script_response.text
    assert "/workspaces?limit=20&offset=0" in script_response.text
    assert "/chat/logs?" in script_response.text
    assert "renderMessageError" in script_response.text
    assert "providerErrorUserMessage" in script_response.text
    assert "Retry" in script_response.text
    assert style_response.status_code == 200
    assert ".chat-panel" in style_response.text
    assert ".knowledge-panel" in style_response.text
    assert ".admin-panel" in style_response.text
    assert ".admin-filter-form" in style_response.text
    assert ".admin-pagination" in style_response.text
    assert ".admin-stat" in style_response.text
    assert ".admin-item" in style_response.text
    assert ".admin-detail" in style_response.text
    assert ".admin-detail-row" in style_response.text
    assert ".message-error" in style_response.text
    assert ".retry-button" in style_response.text
