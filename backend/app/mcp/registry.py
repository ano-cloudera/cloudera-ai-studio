"""MCP connector registry — workspace Settings first, env fallback."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.workspace.mcp_settings import McpServerEntry, enabled_servers, server_by_id


@dataclass(frozen=True)
class McpConnectorConfig:
    id: str
    name: str
    transport: str
    description: str = ""


def _from_workspace_entry(entry: McpServerEntry) -> McpConnectorConfig:
    return McpConnectorConfig(
        id=entry.id,
        name=entry.name,
        transport=entry.transport,
        description=entry.description,
    )


def _legacy_env_connectors(settings: Settings) -> list[McpConnectorConfig]:
    raw = (settings.mcp_connectors_json or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[McpConnectorConfig] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        name = str(item.get("name") or cid).strip()
        if not cid or not name:
            continue
        kind = str(item.get("kind") or "stdio").lower()
        transport = "sse" if kind in {"sse", "http"} else "stdio"
        out.append(
            McpConnectorConfig(
                id=cid,
                name=name,
                transport=transport,
                description=str(item.get("description") or ""),
            )
        )
    return out


def load_mcp_connectors(
    deployment_settings: Settings,
    *,
    workspace_settings_json: dict | None,
) -> list[McpConnectorConfig]:
    ws = [_from_workspace_entry(e) for e in enabled_servers(workspace_settings_json)]
    if ws:
        return ws
    legacy = _legacy_env_connectors(deployment_settings)
    if legacy:
        return legacy
    return [
        McpConnectorConfig(
            id="studio-demo",
            name="Studio Demo (configure MCP in Settings)",
            transport="stdio",
            description="Add an MCP server under Settings → MCP connections.",
        ),
    ]


def resolve_server_entry(
    deployment_settings: Settings,
    *,
    workspace_settings_json: dict | None,
    connector_id: str,
) -> McpServerEntry | None:
    entry = server_by_id(workspace_settings_json, connector_id)
    if entry is not None:
        return entry
    if connector_id == "studio-demo":
        return None
    return None


def connector_by_id(
    deployment_settings: Settings,
    *,
    workspace_settings_json: dict | None,
    connector_id: str,
) -> McpConnectorConfig | None:
    needle = (connector_id or "").strip()
    for row in load_mcp_connectors(deployment_settings, workspace_settings_json=workspace_settings_json):
        if row.id == needle:
            return row
    return None


def connectors_payload(
    deployment_settings: Settings,
    *,
    workspace_settings_json: dict | None,
) -> list[dict[str, Any]]:
    return [
        {
            "id": c.id,
            "name": c.name,
            "transport": c.transport,
            "description": c.description,
        }
        for c in load_mcp_connectors(deployment_settings, workspace_settings_json=workspace_settings_json)
    ]


def new_server_id() -> str:
    return str(uuid.uuid4())
