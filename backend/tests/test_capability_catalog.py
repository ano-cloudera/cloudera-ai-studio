from pathlib import Path

import pytest

from app.ask_data.capability_catalog import (
    legacy_tempo_capability_catalog_enabled,
    resolve_capability_insight_lines,
    resolve_example_questions,
)
from app.core.config import Settings, get_settings


def _enable_legacy_tempo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_DATA_LEGACY_TEMPO_CAPABILITY_CATALOG", "true")
    get_settings.cache_clear()


def test_legacy_tempo_catalog_gated_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASK_DATA_LEGACY_TEMPO_CAPABILITY_CATALOG", raising=False)
    get_settings.cache_clear()
    assert legacy_tempo_capability_catalog_enabled() is False

    _enable_legacy_tempo(monkeypatch)
    assert legacy_tempo_capability_catalog_enabled() is True


def test_tempo_insight_lines_use_nine_domains_only_when_legacy_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.semantic.context import SemanticContextService

    ctx = SemanticContextService()
    default_lines = resolve_capability_insight_lines(ctx, settings=Settings())
    assert not any("TEMPO selama Q4" in line for line in default_lines)

    _enable_legacy_tempo(monkeypatch)
    legacy_lines = resolve_capability_insight_lines(ctx, limit=9, settings=get_settings())
    assert len(legacy_lines) == 9
    assert any("Sales / Sell-In" in line for line in legacy_lines)


def test_banking_runtime_examples_not_tempo(tmp_path: Path) -> None:
    from tests.test_banking_demo_catalog import _auto_banking_ossie
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    questions = resolve_example_questions(ctx, limit=4)
    assert questions
    assert not any("TEMPO" in q or "Alfamart" in q for q in questions)
    lines = resolve_capability_insight_lines(ctx, limit=6)
    assert any("customer" in line.casefold() for line in lines)
