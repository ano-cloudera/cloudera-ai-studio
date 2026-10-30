"""Execute MCP connector tools for Ask Data (@ MCP chip)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.mcp.client import describe_exception, invoke_mcp_server
from app.mcp.planner import PlannedCall, missing_inputs_message, narrate_result, readable_result, plan_tool_call
from app.mcp.registry import connector_by_id, resolve_server_entry

logger = logging.getLogger(__name__)


def _studio_demo_fallback(question: str) -> dict[str, Any]:
    _ = question
    return {
        "message": "Configure MCP servers in Settings → MCP connections (stdio or SSE).",
        "example_stdio": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env_var_names": ["BRAVE_API_KEY"],
        },
    }


async def run_mcp_turn(
    deployment_settings: Settings,
    *,
    workspace_settings_json: dict | None,
    connector_id: str,
    question: str,
    provider: LLMProvider | None = None,
) -> tuple[str, dict[str, Any]]:
    connector = connector_by_id(
        deployment_settings,
        workspace_settings_json=workspace_settings_json,
        connector_id=connector_id,
    )
    if connector is None:
        raise ValueError(f"Unknown MCP connector: {connector_id}")

    entry = resolve_server_entry(
        deployment_settings,
        workspace_settings_json=workspace_settings_json,
        connector_id=connector_id,
    )
    if entry is None:
        if connector_id == "studio-demo":
            payload = {"connector_id": connector_id, "tool": "hint", "result": _studio_demo_fallback(question)}
            answer = f"**MCP**\n\n{payload['result']['message']}"
            return answer, payload
        raise ValueError(f"MCP connector {connector_id!r} is not configured in workspace Settings")

    planner = None
    if provider is not None:
        async def planner(tools: list[Any], text: str):  # noqa: E306
            return await plan_tool_call(provider, text, tools)

    try:
        result = await invoke_mcp_server(entry, question=question, planner=planner)
    except Exception as exc:
        logger.exception("mcp_invoke_failed connector=%s", connector_id)
        raise ValueError(f"MCP call failed: {describe_exception(exc)}") from exc

    if result.get("missing"):
        call = PlannedCall(
            tool=str(result.get("tool") or ""),
            arguments=dict(result.get("arguments") or {}),
            missing=list(result["missing"]),
            descriptions=dict(result.get("descriptions") or {}),
        )
        return missing_inputs_message(call, question), {"connector_id": connector_id, **result}

    content = result.get("content") or json.dumps(result, indent=2)
    narrated = None
    if provider is not None and result.get("content"):
        narrated = await narrate_result(
            provider, question, str(result.get("tool") or ""), dict(result.get("arguments") or {}), content
        )
    answer = narrated or f"**{connector.name}**\n\n{readable_result(content)}"
    return answer, {"connector_id": connector_id, **result}
