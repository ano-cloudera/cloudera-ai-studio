"""'Per month' groups by the date column even when the model did not flag it as a time dimension."""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.semantic.context import SemanticContextService

_DIMS = {"order_id": "String", "order_date": "String", "region_name": "String"}


def _build(flag_time: bool) -> SemanticContextService:
    fields = ""
    for name, datatype in _DIMS.items():
        fields += f"      - name: orders_{name}\n        datatype: {datatype}\n        expression:\n          dialects:\n            - dialect: ANSI_SQL\n              expression: {name}\n"
        if name == "order_date" and flag_time:
            fields += "        dimension:\n          is_time: true\n"
    allowed = ",".join(f'"orders_{name}"' for name in _DIMS)
    root = pathlib.Path(tempfile.mkdtemp()) / "rt"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "reference_core.ossie.yaml").write_text(f'''version: "0.2.0.dev0"
name: orders
description: x
datasets:
  - name: orders
    source: '"hive"."default"."fulfillment_orders"'
    primary_key: [order_id]
    fields:
{fields}metrics:
  - name: total_orders
    description: "Total number of orders."
    ai_context:
      synonyms: ["orders"]
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: COUNT(order_id)
    custom_extensions:
      - vendor_name: REFERENCE
        data: '{{"base_dataset": "orders", "allowed_dimensions": [{allowed}]}}'
''')
    (ossie / "reference_governance.yaml").write_text('unknown_metric_question: "Which?"\n')
    (ossie / "golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


@pytest.mark.parametrize("flag_time", [True, False])
def test_orders_per_month_is_grouped_by_month_in_date_order(flag_time: bool) -> None:
    ctx = _build(flag_time)
    resolution = ctx.resolve("How many orders do we get per month?")
    assert resolution["status"] == "resolved"
    assert resolution["dimensions"] == ["orders_order_date"]
    sql = ctx.compile_governed(resolution["metric"], "How many orders do we get per month?", resolution["dimensions"])
    assert "DATE_TRUNC('month'" in sql
    assert "GROUP BY DATE_TRUNC('month'" in sql
    assert "ORDER BY DATE_TRUNC('month'" in sql and "ASC" in sql


def test_a_period_without_a_year_uses_the_latest_finished_one() -> None:
    from datetime import date

    from app.ask_data.intent_satisfaction import parse_yearless_period

    today = date(2026, 11, 4)
    assert parse_yearless_period("Total orders in March", today).label == "2026-03"
    assert parse_yearless_period("Total orders pada Maret", today).label == "2026-03"
    assert parse_yearless_period("late rate Maret sampai Mei", today).label == "2026-03 to 2026-05"
    assert parse_yearless_period("orders in Q1", today).label == "Q1 2026"
    assert parse_yearless_period("orders in December", today).label == "2025-12"  # this December has not finished


def test_a_year_a_modal_verb_a_comparison_or_no_period_leaves_the_question_alone() -> None:
    from datetime import date

    from app.ask_data.intent_satisfaction import parse_yearless_period

    today = date(2026, 11, 4)
    for question in (
        "Total orders in March 2026",
        "Which regions may have a high late rate?",
        "Compare March and June",
        "Total orders",
        "Orders in March and in June",
    ):
        assert parse_yearless_period(question, today) is None, question


def test_total_orders_in_a_month_without_a_year_gets_a_date_filter() -> None:
    from datetime import date

    ctx = _build(True)
    question = "Total orders in March"
    resolution = ctx.resolve(question)
    sql = ctx.compile_governed(resolution["metric"], question, [])
    year = date.today().year if date.today() >= date(date.today().year, 4, 1) else date.today().year - 1
    assert f"DATE '{year}-03-01'" in sql and f"DATE '{year}-04-01'" in sql
