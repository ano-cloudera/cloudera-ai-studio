from pathlib import Path

import pytest

from app.ask_data.capability_catalog import (
    resolve_capability_insight_lines,
    resolve_example_questions,
)
from app.core.config import Settings, get_settings


def test_banking_runtime_examples_not_reference(tmp_path: Path) -> None:
    from tests.test_banking_demo_catalog import _auto_banking_ossie
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    questions = resolve_example_questions(ctx, limit=4)
    assert questions
    assert not any("REFERENCE" in q or "Acme" in q for q in questions)
    lines = resolve_capability_insight_lines(ctx, limit=6)
    assert any("customer" in line.casefold() for line in lines)


def test_placeholder_reference_metric_is_not_suggested_as_starter():
    from pathlib import Path

    from app.ask_data.capability_catalog import resolve_example_questions
    from app.semantic.context import SemanticContextService

    project = Path(__file__).resolve().parents[1] / "projects" / "reference_impala"
    questions = resolve_example_questions(SemanticContextService(project))
    assert questions
    assert not any("placeholder" in q.casefold() for q in questions)
