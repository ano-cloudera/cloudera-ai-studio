"""Actions the agent may propose: the tools of the workspace's MCP servers that change something (annotation readOnlyHint
false), such as raising a ticket. The agent only proposes; a person approves each one in the chat, and only then is the tool
called (POST /api/v1/mcp/actions/run). Read-only tools (search, lookup, scoring) are never proposed as actions.

Tool lists are kept for a while per server, so proposing costs no extra start of a server. Arguments are checked against the
tool's input schema (required fields, basic types, enum values) both when proposed and when run.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from time import monotonic
from typing import Any

from app.workspace.mcp_settings import McpServerEntry, enabled_servers

logger = logging.getLogger(__name__)

TOOLS_SECONDS = 10 * 60
LIST_TIMEOUT_SECONDS = 15.0
RUN_TIMEOUT_SECONDS = 60.0
_tools: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _attr(item: Any, *names: str) -> Any:
    for name in names:
        value = getattr(item, name, None)
        if value is None and isinstance(item, dict):
            value = item.get(name)
        if value is not None:
            return value
    return None


def _is_action(tool: Any) -> bool:
    annotations = _attr(tool, "annotations")
    if annotations is None:
        return False
    read_only = _attr(annotations, "read_only_hint", "readOnlyHint")
    return read_only is False  # only a tool that says it changes something, never one that says nothing


def _key(entry: McpServerEntry) -> str:
    return f"{entry.id}:{entry.transport}:{entry.command}:{' '.join(entry.args)}:{entry.url}"


async def _session_tools(entry: McpServerEntry) -> list[Any]:
    from mcp import ClientSession

    if entry.transport == "stdio":
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(command=entry.command or "", args=entry.args, env=os.environ.copy())
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return list((await session.list_tools()).tools)
    from mcp.client.sse import sse_client

    from app.mcp.client import _resolve_headers

    async with sse_client((entry.url or "").strip(), headers=_resolve_headers(entry.header_env_var_names) or None) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return list((await session.list_tools()).tools)


async def server_actions(entry: McpServerEntry) -> list[dict[str, Any]]:
    """The action tools of one server: name, description and input schema (kept TOOLS_SECONDS)."""
    key = _key(entry)
    hit = _tools.get(key)
    if hit and monotonic() - hit[0] < TOOLS_SECONDS:
        return hit[1]
    from app.mcp.client import stdio_preflight_problem

    if stdio_preflight_problem(entry):
        return []
    tools = await asyncio.wait_for(_session_tools(entry), timeout=LIST_TIMEOUT_SECONDS)
    actions = [
        {
            "server_id": entry.id,
            "server": entry.name,
            "tool": str(_attr(tool, "name")),
            "description": str(_attr(tool, "description") or "")[:1200],
            "input_schema": _attr(tool, "input_schema", "inputSchema") or {},
        }
        for tool in tools
        if _is_action(tool)
    ]
    _tools[key] = (monotonic(), actions)
    return actions


async def available_actions(servers: list[McpServerEntry]) -> list[dict[str, Any]]:
    """Every action tool of the enabled servers; a server that cannot be reached is left out."""
    found = await asyncio.gather(*(server_actions(s) for s in servers), return_exceptions=True)
    out: list[dict[str, Any]] = []
    for server, result in zip(servers, found):
        if isinstance(result, BaseException):
            logger.warning("mcp_actions_unavailable server=%s error=%s", server.id, type(result).__name__)
            continue
        out.extend(result)
    return out


def check_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    """What is wrong with the arguments for the tool's input schema."""
    problems: list[str] = []
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if arguments.get(name) in (None, ""):
            problems.append(f"'{name}' is required")
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
    for name, value in arguments.items():
        spec = properties.get(name)
        if spec is None:
            problems.append(f"'{name}' is not an argument of this tool")
            continue
        if value is None:
            continue
        options = [spec, *(spec.get("anyOf") or [])]
        allowed = [o.get("type") for o in options if o.get("type") and o.get("type") != "null"]
        enums = [e for o in options for e in (o.get("enum") or [])]
        if allowed and not any(isinstance(value, types.get(t, object)) and not (t in ("integer", "number") and isinstance(value, bool)) for t in allowed):
            problems.append(f"'{name}' must be {' or '.join(allowed)}")
        if enums and value not in enums:
            problems.append(f"'{name}' must be one of {enums}")
    return problems


def proposals(raw: list[Any], actions: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    """The proposed actions that name an available tool with valid arguments, each with an id for the approval."""
    by_tool = {(a["server_id"], a["tool"]): a for a in actions}
    by_name = {a["tool"]: a for a in actions}
    out: list[dict[str, Any]] = []
    for item in raw:
        server_id, tool = str(_attr(item, "server_id") or ""), str(_attr(item, "tool") or "")
        action = by_tool.get((server_id, tool)) or by_name.get(tool)
        arguments = dict(_attr(item, "arguments") or {})
        if action is None:
            logger.info("mcp_action_dropped tool=%s reason=unknown", tool)
            continue
        problems = check_arguments(action["input_schema"], arguments)
        if problems:
            logger.info("mcp_action_dropped tool=%s problems=%s", tool, problems[:3])
            continue
        out.append({
            "id": uuid.uuid4().hex[:12],
            "server_id": action["server_id"],
            "server": action["server"],
            "tool": action["tool"],
            "title": " ".join(str(_attr(item, "title") or action["tool"]).split())[:160],
            "arguments": arguments,
        })
        if len(out) >= limit:
            break
    return out


async def run_action(entry: McpServerEntry, tool: str, arguments: dict[str, Any]) -> str:
    """Call an approved action. The tool must still be an action of the server and the arguments must still be valid."""
    actions = {a["tool"]: a for a in await server_actions(entry)}
    action = actions.get(tool)
    if action is None:
        raise ValueError(f"'{tool}' is not an action of {entry.name}")
    problems = check_arguments(action["input_schema"], arguments)
    if problems:
        raise ValueError("; ".join(problems))
    from mcp import ClientSession

    from app.mcp.client import _content_to_text

    async def call() -> str:
        if entry.transport == "stdio":
            from mcp.client.stdio import StdioServerParameters, stdio_client

            params = StdioServerParameters(command=entry.command or "", args=entry.args, env=os.environ.copy())
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return _content_to_text(await session.call_tool(tool, arguments=arguments))
        from mcp.client.sse import sse_client

        from app.mcp.client import _resolve_headers

        async with sse_client((entry.url or "").strip(), headers=_resolve_headers(entry.header_env_var_names) or None) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return _content_to_text(await session.call_tool(tool, arguments=arguments))

    logger.info("mcp_action_run server=%s tool=%s", entry.id, tool)
    return await asyncio.wait_for(call(), timeout=RUN_TIMEOUT_SECONDS)


def workspace_servers(settings_json: dict[str, Any] | None) -> list[McpServerEntry]:
    return enabled_servers(settings_json)


def clear_cache() -> None:
    _tools.clear()
