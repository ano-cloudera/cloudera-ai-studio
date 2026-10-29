"""MCP protocol client (stdio + SSE) using the official MCP Python SDK."""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

from app.workspace.mcp_settings import McpServerEntry

logger = logging.getLogger(__name__)


def _resolve_env(env_var_names: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in env_var_names:
        val = os.environ.get(key, "").strip()
        if val:
            out[key] = val
    return out


def _resolve_headers(header_env: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for header, env_key in header_env.items():
        val = os.environ.get(env_key, "").strip()
        if val:
            out[header] = val
    return out


def _pick_tool(tools: list[Any], question: str, default_tool: str | None) -> tuple[str, dict[str, Any]]:
    names = [getattr(t, "name", None) or t.get("name") for t in tools if getattr(t, "name", None) or t.get("name")]
    if default_tool and default_tool in names:
        return default_tool, _arguments_for_tool(default_tool, question)
    lower = question.lower()
    for hint in ("search", "brave", "web", "query"):
        if hint in lower:
            for name in names:
                if hint in name.lower() or "search" in name.lower():
                    return name, _arguments_for_tool(name, question)
    if names:
        first = str(names[0])
        return first, _arguments_for_tool(first, question)
    raise ValueError("MCP server returned no tools")


def _arguments_for_tool(tool_name: str, question: str) -> dict[str, Any]:
    if re.search(r"search|brave|web", tool_name, re.I):
        return {"query": question.strip()}
    if "time" in tool_name.lower():
        return {}
    return {"input": question.strip(), "query": question.strip(), "question": question.strip()}


def _content_to_text(result: Any) -> str:
    content = getattr(result, "content", None) or (result.get("content") if isinstance(result, dict) else None)
    if not content:
        return str(result)
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(str(text))
    return "\n\n".join(parts) if parts else str(result)


def describe_exception(exc: BaseException) -> str:
    """The real cause behind an ExceptionGroup ("unhandled errors in a TaskGroup") raised by the MCP transport."""
    parts: list[str] = []

    def walk(error: BaseException) -> None:
        children = getattr(error, "exceptions", None)
        if children:
            for child in children:
                walk(child)
            return
        text = str(error).strip() or type(error).__name__
        if text not in parts:
            parts.append(text)

    walk(exc)
    return "; ".join(parts)


def stdio_preflight_problem(entry: McpServerEntry) -> str | None:
    """A readable reason when a stdio server cannot even start (missing command or script), else None."""
    if entry.transport != "stdio":
        return None
    command = (entry.command or "").strip()
    if not command:
        return "No command is configured for this stdio server."
    if "/" in command:
        if not Path(command).exists():
            return f"Command not found: {command}"
    elif shutil.which(command) is None:
        return f"Command not found on the backend PATH: {command}"
    for arg in entry.args:
        if arg.startswith("/") and arg.endswith((".py", ".js", ".mjs")) and not Path(arg).exists():
            return f"Server script not found: {arg}"
    return None


def missing_mcp_env_vars(entry: McpServerEntry) -> list[str]:
    missing: list[str] = []
    for key in entry.env_var_names:
        if not os.environ.get(key, "").strip():
            missing.append(key)
    for env_key in entry.header_env_var_names.values():
        if env_key and not os.environ.get(env_key, "").strip():
            missing.append(env_key)
    return sorted(set(missing))


async def probe_mcp_server(entry: McpServerEntry) -> dict[str, Any]:
    """Initialize MCP session and list tools (no tool invocation)."""
    from mcp import ClientSession

    missing = missing_mcp_env_vars(entry)
    if missing:
        return {
            "ok": False,
            "message": f"Missing backend environment variables: {', '.join(missing)}",
            "tools": [],
            "latency_ms": 0,
            "missing_env_var_names": missing,
        }

    problem = stdio_preflight_problem(entry)
    if problem:
        return {"ok": False, "message": problem, "tools": [], "latency_ms": 0, "missing_env_var_names": []}

    started = time.monotonic()

    async def _list_tools(read: Any, write: Any) -> list[str]:
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = listed.tools
            names: list[str] = []
            for t in tools:
                name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
                if name:
                    names.append(str(name))
            return names

    try:
        if entry.transport == "stdio":
            from mcp.client.stdio import StdioServerParameters, stdio_client

            params = StdioServerParameters(
                command=entry.command or "",
                args=entry.args,
                env={**os.environ.copy(), **_resolve_env(entry.env_var_names)},
            )
            async with stdio_client(params) as (read, write):
                names = await _list_tools(read, write)
        elif entry.transport == "sse":
            from mcp.client.sse import sse_client

            url = (entry.url or "").strip()
            headers = _resolve_headers(entry.header_env_var_names)
            async with sse_client(url, headers=headers or None) as (read, write):
                names = await _list_tools(read, write)
        else:
            raise ValueError(f"Unsupported MCP transport: {entry.transport}")

        latency_ms = int((time.monotonic() - started) * 1000)
        if not names:
            return {
                "ok": False,
                "message": "Connected but the server returned no tools.",
                "tools": [],
                "latency_ms": latency_ms,
                "missing_env_var_names": [],
            }
        preview = ", ".join(names[:8])
        if len(names) > 8:
            preview += f", +{len(names) - 8} more"
        return {
            "ok": True,
            "message": f"Connected ({len(names)} tool{'s' if len(names) != 1 else ''}: {preview})",
            "tools": names,
            "latency_ms": latency_ms,
            "missing_env_var_names": [],
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        message = describe_exception(exc)
        logger.warning("mcp_probe_failed server=%s err=%s", entry.id, message)
        return {
            "ok": False,
            "message": message,
            "tools": [],
            "latency_ms": latency_ms,
            "missing_env_var_names": [],
        }


async def _run_session(session: Any, entry: McpServerEntry, question: str, planner: Any) -> dict[str, Any]:
    """Initialize, pick the tool and arguments (planner first, keyword fallback), call it."""
    await session.initialize()
    tools = (await session.list_tools()).tools
    planned = None
    if planner is not None:
        try:
            planned = await planner(tools, question)
        except Exception:  # noqa: BLE001 - a failed plan must degrade to the keyword picker, not fail the turn
            logger.warning("mcp_plan_failed server=%s", entry.id, exc_info=True)
    if planned is not None:
        if planned.missing:
            return {
                "server_id": entry.id,
                "tool": planned.tool,
                "arguments": planned.arguments,
                "missing": planned.missing,
                "descriptions": planned.descriptions,
                "content": "",
            }
        tool_name, arguments = planned.tool, planned.arguments
    else:
        tool_name, arguments = _pick_tool(tools, question, entry.default_tool)
    logger.info("mcp_call server=%s tool=%s planned=%s", entry.id, tool_name, planned is not None)
    result = await session.call_tool(tool_name, arguments=arguments)
    return {
        "server_id": entry.id,
        "tool": tool_name,
        "arguments": arguments,
        "content": _content_to_text(result),
    }


async def invoke_mcp_server(entry: McpServerEntry, *, question: str, planner: Any = None) -> dict[str, Any]:
    """Call one tool of the server. `planner(tools, question)` may return a PlannedCall with typed arguments."""
    from mcp import ClientSession

    problem = stdio_preflight_problem(entry)
    if problem:
        raise ValueError(problem)

    if entry.transport == "stdio":
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=entry.command or "",
            args=entry.args,
            env={**os.environ.copy(), **_resolve_env(entry.env_var_names)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                return await _run_session(session, entry, question, planner)

    if entry.transport == "sse":
        from mcp.client.sse import sse_client

        url = (entry.url or "").strip()
        headers = _resolve_headers(entry.header_env_var_names)
        async with sse_client(url, headers=headers or None) as (read, write):
            async with ClientSession(read, write) as session:
                return await _run_session(session, entry, question, planner)

    raise ValueError(f"Unsupported MCP transport: {entry.transport}")
