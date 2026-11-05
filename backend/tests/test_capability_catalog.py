from pathlib import Path

import pytest

from app.ask_data.capability_catalog import (
    resolve_capability_insight_lines,
    resolve_example_questions,
)
from app.core.config import Settings, get_settings


def test_a_published_model_suggests_questions_about_its_own_metrics() -> None:
    from replay_support import build_context

    ctx = build_context()
    questions = resolve_example_questions(ctx, limit=4)
    assert questions
    lines = resolve_capability_insight_lines(ctx, limit=6)
    assert any("late" in line.casefold() for line in lines)
    assert not any("REFERENCE" in line or "Acme" in line for line in lines)


def test_placeholder_reference_metric_is_not_suggested_as_starter():
    from pathlib import Path

    from app.ask_data.capability_catalog import resolve_example_questions
    from app.semantic.context import SemanticContextService

    project = Path(__file__).resolve().parents[1] / "projects" / "reference_impala"
    questions = resolve_example_questions(SemanticContextService(project))
    assert questions
    assert not any("placeholder" in q.casefold() for q in questions)
