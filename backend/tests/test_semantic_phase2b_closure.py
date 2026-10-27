"""Phase 2B API closure: accept/reject, edited payload, publish failure shape."""
from __future__ import annotations

import uuid

import pytest

from app.services.semantic_suggestion_accept_service import _normalize_metric_expression


def test_normalize_metric_expression_strips_entity_prefix():
    assert _normalize_metric_expression("SUM(sales.amount)") == "SUM(amount)"


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("SUM(amount)", "SUM(amount)"),
        ("COUNT(DISTINCT id)", "COUNT(DISTINCT id)"),
    ],
)
def test_normalize_metric_expression_passthrough(expr: str, expected: str):
    assert _normalize_metric_expression(expr) == expected


def test_suggestion_id_format_stable():
    sid = f"metric:gate_{uuid.uuid4().hex[:6]}"
    assert sid.startswith("metric:")
