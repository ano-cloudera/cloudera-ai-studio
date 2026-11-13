#!/usr/bin/env python3
"""MCP server (stdio): an operations desk where follow-up tickets are raised and listed.

The agent proposes a ticket from what the data showed (which terminal or region, how far off, by when); the user approves it in
the chat and only then is create_ticket called. Tickets are kept in a JSON file (OPS_DESK_FILE, default
~/anywhere-studio-data/ops_desk/tickets.json, which is the project storage on Cloudera AI). To send them to a real system
(ServiceNow, Jira, SAP PM, email), replace _save() with a call to it; the tools and the agent stay unchanged.

Register it in Settings -> MCP connections as a stdio server:
    command: <python of the backend venv>     args: scripts/mcp/ops_desk_server.py

create_ticket is annotated as an action (readOnlyHint false), which is how the agent knows it may propose it; list_tickets is
read-only. Works with mcp 1.x (FastMCP) and 2.x (MCPServer).
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ImportError:  # mcp 2.x renamed it
    from mcp.server.mcpserver import MCPServer as _Server
from mcp.types import ToolAnnotations


def _annotations(read_only: bool) -> ToolAnnotations:
    try:
        return ToolAnnotations(readOnlyHint=read_only, destructiveHint=False, idempotentHint=False, openWorldHint=False)
    except Exception:  # noqa: BLE001 - a version that only takes the field names
        return ToolAnnotations(read_only_hint=read_only, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


server = _Server("Operations Desk")
PRIORITIES = ("low", "medium", "high", "critical")


def _file() -> Path:
    explicit = os.environ.get("OPS_DESK_FILE", "").strip()
    return Path(explicit) if explicit else Path.home() / "anywhere-studio-data" / "ops_desk" / "tickets.json"


def _load() -> list[dict]:
    path = _file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(tickets: list[dict]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
        json.dump(tickets, handle, ensure_ascii=False, indent=2)
        temp = handle.name
    os.replace(temp, path)  # never a half-written file


@server.tool(annotations=_annotations(read_only=False))
def create_ticket(
    title: str,
    description: str,
    priority: Literal["low", "medium", "high", "critical"] = "medium",
    location: str | None = None,
    assignee_role: str | None = None,
    due_in_days: int = 7,
    evidence: str | None = None,
) -> str:
    """Raise a follow-up ticket for an operational issue found in the data, for a team to act on.

    title: short, names the issue and the place ("Investigate late deliveries at terminal X").
    description: what to do and why, in one to three sentences.
    priority: low, medium, high or critical. location: the region, terminal, site or customer it is about.
    assignee_role: the role that should act ("Terminal manager", "Regional distribution lead").
    due_in_days: when it should be done, in days from today (1 to 90).
    evidence: the figures that justify it, as found in the data ("late rate 36.3% against 16.1% overall").
    Returns the ticket with its id.
    """
    title = " ".join(str(title).split())[:160]
    if not title:
        return json.dumps({"error": "title is required"})
    if priority not in PRIORITIES:
        return json.dumps({"error": f"priority must be one of {', '.join(PRIORITIES)}"})
    days = max(1, min(90, int(due_in_days or 7)))
    tickets = _load()
    ticket = {
        "id": f"OPS-{date.today():%y%m%d}-{uuid.uuid4().hex[:4].upper()}",
        "title": title,
        "description": " ".join(str(description).split())[:1200],
        "priority": priority,
        "location": (location or "").strip()[:160] or None,
        "assignee_role": (assignee_role or "").strip()[:120] or None,
        "due_date": (date.today() + timedelta(days=days)).isoformat(),
        "evidence": (evidence or "").strip()[:600] or None,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tickets.append(ticket)
    _save(tickets)
    return json.dumps({"created": ticket}, ensure_ascii=False, indent=2)


@server.tool(annotations=_annotations(read_only=True))
def list_tickets(status: Literal["open", "closed", "all"] = "open", location: str | None = None, limit: int = 20) -> str:
    """List follow-up tickets, newest first. status: open, closed or all. location: only tickets about this place."""
    tickets = _load()
    if status != "all":
        tickets = [t for t in tickets if t.get("status") == status]
    if location:
        needle = location.casefold()
        tickets = [t for t in tickets if needle in str(t.get("location") or "").casefold()]
    tickets = sorted(tickets, key=lambda t: str(t.get("created_at")), reverse=True)[: max(1, min(100, int(limit or 20)))]
    return json.dumps({"tickets": tickets, "count": len(tickets)}, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    server.run(transport="stdio")
