"""Actions the agent may propose: only MCP tools that say they change something, with arguments valid for their schema, and
run only when approved. The Operations Desk server is started for real over stdio."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from app.mcp import actions
from app.workspace.mcp_settings import McpServerEntry

REPO = Path(__file__).resolve().parents[2]
SCHEMA = {
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "priority": {"enum": ["low", "medium", "high", "critical"], "type": "string"},
        "due_in_days": {"type": "integer"},
        "location": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["title", "description"],
}
ACTION = {"server_id": "ops", "server": "Operations Desk", "tool": "create_ticket", "description": "", "input_schema": SCHEMA}


def test_arguments_are_checked_against_the_schema() -> None:
    assert actions.check_arguments(SCHEMA, {"title": "x", "description": "y", "priority": "high", "location": None}) == []
    problems = actions.check_arguments(SCHEMA, {"title": "x", "priority": "urgent", "due_in_days": "3", "colour": "red"})
    assert any("description" in p for p in problems) and any("priority" in p for p in problems)
    assert any("due_in_days" in p for p in problems) and any("colour" in p for p in problems)
    assert actions.check_arguments(SCHEMA, {"title": "x", "description": "y", "due_in_days": True})  # a bool is not a number


def test_only_valid_proposals_of_known_tools_are_kept() -> None:
    raw = [
        {"server_id": "ops", "tool": "create_ticket", "title": "Buat tiket Sorong", "arguments": {"title": "Sorong", "description": "cek armada"}},
        {"server_id": "ops", "tool": "create_ticket", "title": "no description", "arguments": {"title": "x"}},
        {"server_id": "ops", "tool": "delete_everything", "arguments": {}},
    ]
    kept = actions.proposals(raw, [ACTION])
    assert len(kept) == 1 and kept[0]["title"] == "Buat tiket Sorong" and kept[0]["id"]


def test_a_tool_is_an_action_only_when_it_says_it_changes_something() -> None:
    class Annotated:
        def __init__(self, **hints):
            self.annotations = type("A", (), hints)()

    assert actions._is_action(Annotated(read_only_hint=False))
    assert not actions._is_action(Annotated(read_only_hint=True))
    assert not actions._is_action(type("T", (), {"annotations": None})())  # says nothing: never proposed


@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv("OPS_DESK_FILE", str(tmp_path / "tickets.json"))
    actions.clear_cache()
    yield McpServerEntry(id="ops", name="Operations Desk", transport="stdio", command=sys.executable, args=[str(REPO / "scripts" / "mcp" / "ops_desk_server.py")])
    actions.clear_cache()


def test_the_operations_desk_lists_its_action_and_runs_it_when_approved(desk, tmp_path) -> None:
    found = asyncio.run(actions.server_actions(desk))
    assert [a["tool"] for a in found] == ["create_ticket"]  # list_tickets is read-only
    assert [t["tool"] for t in asyncio.run(actions.server_reads(desk))] == ["list_tickets"]
    result = asyncio.run(actions.run_action(desk, "create_ticket", {"title": "Cek Sorong", "description": "armada", "priority": "high", "location": "Sorong"}))
    created = json.loads(result)["created"]
    assert created["id"].startswith("OPS-") and created["priority"] == "high"
    assert json.loads((tmp_path / "tickets.json").read_text())[0]["location"] == "Sorong"
    with pytest.raises(ValueError):
        asyncio.run(actions.run_action(desk, "list_tickets", {}))  # not an action
    with pytest.raises(ValueError):
        asyncio.run(actions.run_action(desk, "create_ticket", {"title": "no description"}))


def test_a_read_only_tool_lists_what_was_created_and_an_action_cannot_be_read_as_a_lookup(desk) -> None:
    asyncio.run(actions.run_action(desk, "create_ticket", {"title": "Cek Sorong", "description": "armada", "priority": "high", "location": "Sorong"}))
    listed = json.loads(asyncio.run(actions.run_read(desk, "list_tickets", {"status": "open"})))
    assert listed["count"] == 1 and listed["tickets"][0]["location"] == "Sorong"
    with pytest.raises(ValueError):
        asyncio.run(actions.run_read(desk, "create_ticket", {"title": "x", "description": "y"}))  # it changes something
