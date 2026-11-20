from app.prompt_management import managed


def _patch(monkeypatch, extra: str):
    texts = {"ask_data.agent": "CORE RULES", managed.WORKSPACE_KEY: extra}
    monkeypatch.setattr(managed, "_resolved", lambda key, file_name: texts[key])


def test_without_workspace_instructions_the_prompt_is_unchanged(monkeypatch) -> None:
    _patch(monkeypatch, "  ")
    assert managed.managed_prompt("ask_data.agent", "agent_tools.md") == "CORE RULES"


def test_workspace_instructions_are_added_after_the_core_prompt(monkeypatch) -> None:
    _patch(monkeypatch, "Answer in formal Indonesian.")
    text = managed.managed_prompt("ask_data.agent", "agent_tools.md")
    assert text.startswith("CORE RULES") and text.rstrip().endswith("Answer in formal Indonesian.")
    assert "the rules above win" in text


def test_the_instructions_prompt_itself_is_not_wrapped(monkeypatch) -> None:
    _patch(monkeypatch, "Be brief.")
    assert managed.managed_prompt(managed.WORKSPACE_KEY, "workspace_instructions.md") == "Be brief."


def test_the_default_file_is_empty() -> None:
    assert (managed.PROMPT_DIR / "workspace_instructions.md").read_text().strip() == ""
