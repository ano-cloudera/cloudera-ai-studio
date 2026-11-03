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
