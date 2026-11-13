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
    yield McpServerEntry(id="ops", name="Operations Desk", transport="stdio", command=sys.executable, args=[str(REPO / "samples" / "ops_desk" / "ops_desk_server.py")])
    actions.clear_cache()


def test_the_operations_desk_lists_its_action_and_runs_it_when_approved(desk, tmp_path) -> None:
    found = asyncio.run(actions.server_actions(desk))
    assert [a["tool"] for a in found] == ["create_ticket"]  # list_tickets is read-only
    result = asyncio.run(actions.run_action(desk, "create_ticket", {"title": "Cek Sorong", "description": "armada", "priority": "high", "location": "Sorong"}))
    created = json.loads(result)["created"]
    assert created["id"].startswith("OPS-") and created["priority"] == "high"
    assert json.loads((tmp_path / "tickets.json").read_text())[0]["location"] == "Sorong"
    with pytest.raises(ValueError):
        asyncio.run(actions.run_action(desk, "list_tickets", {}))  # not an action
    with pytest.raises(ValueError):
        asyncio.run(actions.run_action(desk, "create_ticket", {"title": "no description"}))


def test_every_approved_action_is_recorded_whether_it_ran_or_not(tmp_path) -> None:
    from types import SimpleNamespace

    from app.mcp import action_log

    settings = SimpleNamespace(answer_cache_dir=str(tmp_path / "cache" / "answers"))
    action_log.clear_memory()
    action_log.record(settings, server_id="ops", server="Operations Desk", tool="create_ticket", title="Open a ticket", arguments={"title": "x"}, ok=True, result='{"created": {"id": "OPS-1"}}')
    action_log.record(settings, server_id="ops", server="Operations Desk", tool="create_ticket", title=None, arguments={}, ok=False, error="'title' is required")
    action_log.clear_memory()  # a restart: the record is on disk
    listed = action_log.history(settings)
    assert [e["status"] for e in listed] == ["failed", "ok"]  # newest first
    assert listed[1]["arguments"] == {"title": "x"} and listed[1]["title"] == "Open a ticket" and listed[0]["title"] == "create_ticket"
    assert action_log.count(settings) == 2 and (tmp_path / "cache" / "actions").exists()


def test_the_endpoints_run_record_and_say_when_the_actions_page_has_something_to_show(desk, tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1 import mcp as mcp_api
    from app.mcp import action_log

    action_log.clear_memory()
    settings = SimpleNamespace(answer_cache_dir=str(tmp_path / "cache" / "answers"))

    class Chat:
        def mcp_servers(self):
            return [desk]

        async def agent_actions(self):
            return await actions.available_actions([desk])

    app = FastAPI()
    app.include_router(mcp_api.router, prefix="/api/v1")
    app.state.settings, app.state.chat_service = settings, Chat()
    client = TestClient(app)
    status = client.get("/api/v1/mcp/actions/status").json()
    assert status == {"visible": True, "recorded": 0, "action_tools_available": True}  # a server offers an action: page shown
    ok = client.post("/api/v1/mcp/actions/run", json={"server_id": "ops", "tool": "create_ticket", "title": "Open a ticket for Sorong", "arguments": {"title": "Sorong", "description": "audit", "priority": "high"}})
    assert ok.status_code == 200 and ok.json()["record_id"]
    bad = client.post("/api/v1/mcp/actions/run", json={"server_id": "ops", "tool": "create_ticket", "arguments": {"title": "no description"}})
    assert bad.status_code == 422
    assert client.post("/api/v1/mcp/actions/run", json={"server_id": "nope", "tool": "create_ticket", "arguments": {}}).status_code == 404
    listed = client.get("/api/v1/mcp/actions/history").json()["actions"]
    assert [e["status"] for e in listed] == ["failed", "ok"] and listed[1]["title"] == "Open a ticket for Sorong"
    assert client.get("/api/v1/mcp/actions/status").json()["recorded"] == 2


def test_a_record_can_be_deleted_and_keeps_how_long_it_took_and_which_answer_proposed_it(tmp_path) -> None:
    from types import SimpleNamespace

    from app.mcp import action_log

    settings = SimpleNamespace(project_storage_dir=None, answer_cache_dir=str(tmp_path / "answers"))
    action_log.clear_memory()
    one = action_log.record(settings, server_id="ops", server="Operations Desk", tool="create_ticket", title="A", arguments={}, ok=True, duration_ms=830, request_id="req-1")
    two = action_log.record(settings, server_id="ops", server="Operations Desk", tool="create_ticket", title="B", arguments={}, ok=False, error="down")
    kept = {row["id"]: row for row in action_log.history(settings)}
    assert kept[one["id"]]["duration_ms"] == 830 and kept[one["id"]]["request_id"] == "req-1"
    assert action_log.delete(settings, [one["id"], "nope"]) == 1
    assert [row["id"] for row in action_log.history(settings)] == [two["id"]]
    assert action_log.delete(settings, [one["id"]]) == 0  # already gone
    action_log.clear_memory()
