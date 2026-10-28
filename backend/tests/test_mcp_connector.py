"""MCP workspace settings and chat routing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.mcp.registry import connector_by_id, load_mcp_connectors
from app.workspace.mcp_settings import McpServerEntry, McpWorkspaceSettings, write_mcp_settings


@pytest.fixture
def settings() -> Settings:
    return Settings(mcp_connectors_json="")


def test_workspace_mcp_server_in_registry(settings: Settings) -> None:
    ws = write_mcp_settings(
        None,
        McpWorkspaceSettings(
            servers=[
                McpServerEntry(
                    id="brave-1",
                    name="Brave Search",
                    transport="stdio",
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-brave-search"],
                    env_var_names=["BRAVE_API_KEY"],
                )
            ]
        ),
    )
    rows = load_mcp_connectors(settings, workspace_settings_json=ws)
    assert any(r.id == "brave-1" for r in rows)
    assert connector_by_id(settings, workspace_settings_json=ws, connector_id="brave-1") is not None


def test_mcp_test_connection_api(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_probe(entry: McpServerEntry) -> dict:
        assert entry.name == "Brave"
        return {
            "ok": True,
            "message": "Connected (1 tool: search)",
            "tools": ["search"],
            "latency_ms": 12,
            "missing_env_var_names": [],
        }

    monkeypatch.setattr("app.api.v1.mcp.probe_mcp_server", fake_probe)
    app = create_app(Settings(mcp_connectors_json=""))
    client = TestClient(app)
    body = {
        "id": "x",
        "name": "Brave",
        "enabled": True,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env_var_names": ["BRAVE_API_KEY"],
        "description": "",
        "url": None,
        "header_env_var_names": {},
        "default_tool": None,
    }
    resp = client.post("/api/v1/mcp/test-connection", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["tools"] == ["search"]


def test_mcp_settings_api_roundtrip() -> None:
    app = create_app(Settings(mcp_connectors_json=""))
    client = TestClient(app)
    body = {
        "servers": [
            {
                "id": "x",
                "name": "Brave",
                "enabled": True,
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                "env_var_names": ["BRAVE_API_KEY"],
                "description": "",
                "url": None,
                "header_env_var_names": {},
                "default_tool": None,
            }
        ]
    }
    put = client.put("/api/v1/mcp/settings?workspace_slug=default", json=body)
    assert put.status_code == 200, put.text
    get = client.get("/api/v1/mcp/settings?workspace_slug=default")
    assert get.status_code == 200
    assert get.json()["settings"]["servers"][0]["name"] == "Brave"
    connectors = client.get("/api/v1/mcp/connectors?workspace_slug=default")
    assert connectors.status_code == 200
    assert any(c["id"] == "x" for c in connectors.json().get("connectors") or [])
