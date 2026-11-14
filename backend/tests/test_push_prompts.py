"""scripts/push_prompts.py puts a prompt file into the Prompts feature through its API, without touching what is already the same."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("push_prompts_under_test", ROOT / "scripts" / "push_prompts.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["push_prompts_under_test"] = module
    spec.loader.exec_module(module)
    return module


class FakeApi:
    """The Prompts API as far as the script uses it: prompts with versions, one of them active."""

    def __init__(self, prompts=None):
        self.prompts = prompts or {}  # id -> {"row": {...}, "versions": [...]}
        self.calls: list[tuple[str, str]] = []

    def call(self, method, path, body=None, **_):
        self.calls.append((method, path))
        if method == "GET" and path.startswith("/api/v1/prompts?scope="):
            return {"prompts": [p["row"] for p in self.prompts.values()]}
        if method == "GET" and path.endswith("/versions"):
            pid = path.split("/")[4]
            return {"versions": sorted(self.prompts[pid]["versions"], key=lambda v: -v["version_number"])}
        if method == "POST" and path == "/api/v1/prompts":
            pid = f"p{len(self.prompts) + 1}"
            self.prompts[pid] = {"row": {"id": pid, "key": body["key"], "scope": body["scope"]}, "versions": [{"id": "v1", "version_number": 1, "status": "DRAFT", "content": body["initial_content"]}]}
            return {"prompt": self.prompts[pid]["row"]}
        if method == "POST" and path.endswith("/versions"):
            pid = path.split("/")[4]
            versions = self.prompts[pid]["versions"]
            version = {"id": f"v{len(versions) + 1}", "version_number": len(versions) + 1, "status": "DRAFT", "content": body["content"]}
            versions.append(version)
            return {"version": version}
        if method == "POST" and path.endswith("/publish"):
            pid, vid = path.split("/")[4], path.split("/")[6]
            for version in self.prompts[pid]["versions"]:
                version["status"] = "ACTIVE" if version["id"] == vid else ("ARCHIVED" if version["status"] == "ACTIVE" else version["status"])
            return {"version": {"id": vid}}
        raise AssertionError((method, path))


def test_a_missing_prompt_is_created_and_published_and_one_already_the_same_is_left_alone() -> None:
    script = _load()
    api = FakeApi()
    assert "created and published version 1" in script.push(api, "rag.system", "Answer from evidence.", "global", dry_run=False)
    assert api.prompts["p1"]["versions"][0]["status"] == "ACTIVE"
    before = list(api.calls)
    assert "already active" in script.push(api, "rag.system", "Answer from evidence.\n", "global", dry_run=False)
    assert not [c for c in api.calls[len(before):] if c[0] == "POST"]  # nothing written the second time


def test_a_changed_file_becomes_a_new_active_version_and_the_old_one_is_kept() -> None:
    script = _load()
    api = FakeApi({"p1": {"row": {"id": "p1", "key": "rag.system", "scope": "global"}, "versions": [{"id": "v1", "version_number": 1, "status": "ACTIVE", "content": "old"}]}})
    message = script.push(api, "rag.system", "new", "global", dry_run=False)
    assert "published version 2" in message
    statuses = {v["version_number"]: v["status"] for v in api.prompts["p1"]["versions"]}
    assert statuses == {1: "ARCHIVED", 2: "ACTIVE"}  # the old text stays in the history, so it can be rolled back


def test_a_dry_run_writes_nothing() -> None:
    script = _load()
    api = FakeApi({"p1": {"row": {"id": "p1", "key": "rag.system", "scope": "global"}, "versions": [{"id": "v1", "version_number": 1, "status": "ACTIVE", "content": "old"}]}})
    assert "would add version 2" in script.push(api, "rag.system", "new", "global", dry_run=True)
    assert not [c for c in api.calls if c[0] == "POST"]


def test_every_pushed_key_has_a_file_and_the_script_runs_offline_for_a_dry_run(capsys) -> None:
    script = _load()
    for filename in script.FILES.values():
        assert (script.PROMPT_DIR / filename).is_file()
    assert script.main(["--dry-run", "--key", "rag.system"]) == 0
    assert "would push rag_system.txt" in capsys.readouterr().out


def test_the_prompts_that_write_a_data_answer_are_managed_keys_with_a_file_default(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.prompt_management import managed
    from app.prompt_management.keys import KNOWN_PROMPT_KEYS
    from app.prompt_management.sources import FilePromptSource

    script = _load()
    for key in ("ask_data.analyst", "ask_data.agent", "ask_data.agent_report", "ask_data.turn_reader"):
        assert key in KNOWN_PROMPT_KEYS and key in script.FILES
        assert FilePromptSource.FILE_MAP[key] == script.FILES[key]  # the script pushes the file the platform falls back to
        assert (managed.PROMPT_DIR / script.FILES[key]).is_file()

    # A published version wins over the file; a prompt that cannot be resolved falls back to the file instead of stopping an answer.
    class Winner:
        def __init__(self, *_a, **_k): ...
        def resolve(self, key):
            return SimpleNamespace(content="  published text  ")

    class Broken(Winner):
        def resolve(self, key):
            raise RuntimeError("no database")

    monkeypatch.setattr("app.prompt_management.resolver.PromptResolver", Winner)
    assert managed.managed_prompt("ask_data.analyst", "result_analyst.md") == "published text"
    monkeypatch.setattr("app.prompt_management.resolver.PromptResolver", Broken)
    assert "AnalysisOutput" in managed.managed_prompt("ask_data.analyst", "result_analyst.md")


def test_status_warns_when_a_more_specific_prompt_overrides_what_was_pushed() -> None:
    script = _load()

    class Resolving:
        def call(self, method, path, body=None, **_):
            return {"source": "workspace", "source_label": "Workspace override", "content": "x", "layers": [{"scope": "workspace", "version_number": 1}, {"scope": "global", "version_number": 1}]}

    line = script.status(Resolving(), "rag.system", "y", "global")
    assert "WARNING: a workspace prompt overrides what was pushed at global" in line
    assert "NOTE" in script.status(Resolving(), "rag.system", "y", "workspace")  # two scopes hold the key
