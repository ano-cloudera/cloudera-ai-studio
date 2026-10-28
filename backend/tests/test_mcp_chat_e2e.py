"""MCP @ chip chat path (in-process)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.platform_engine import get_session_factory
from app.db.platform_models import WorkspaceRow
from app.main import create_app
from app.workspace.mcp_settings import McpWorkspaceSettings, write_mcp_settings

@pytest.fixture
def chat_client() -> TestClient:
    from app.core.config import Settings

    app = create_app(Settings(mcp_connectors_json=""))
    url = app.state.settings.database_url
    if not url:
        pytest.skip("DATABASE_URL required")
    ws_json = write_mcp_settings(None, McpWorkspaceSettings(servers=[]))
    factory = get_session_factory(url)
    with factory() as session:
        row = session.execute(select(WorkspaceRow).where(WorkspaceRow.slug == "default")).scalar_one_or_none()
        if row is None:
            pytest.skip("default workspace missing")
        row.settings_json = ws_json
        session.add(row)
        session.commit()
    return TestClient(app)


def test_mcp_settings_and_chat_placeholder(chat_client: TestClient) -> None:
    settings = chat_client.get("/api/v1/mcp/settings")
    assert settings.status_code == 200
    connectors = chat_client.get("/api/v1/mcp/connectors").json().get("connectors") or []
    assert connectors
    cid = connectors[0]["id"]
    body = {
        "session_id": f"mcp-test-{uuid.uuid4()}",
        "question": "What is our stack?",
        "provider": "gemini",
        "model": "not-used-for-mcp",
        "context_sources": [{"type": "mcp_connector", "id": cid, "name": connectors[0]["name"]}],
    }
    response = chat_client.post("/chat", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("status") == "SUCCESS"
    assert data.get("strategy") == "mcp"
    assert data.get("answer")
