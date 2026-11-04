"""A question that says "order" must find the metric aliased "orders", not a weaker partial match."""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.semantic.context import SemanticContextService

_FIELDS = {"order_id": "String", "order_date": "String", "order_value": "Number", "region_name": "String"}


def _metric(name: str, desc: str, synonyms: str, expr: str, allowed: str) -> str:
    return f'''  - name: {name}
    description: "{desc}"
    ai_context:
      synonyms: {synonyms}
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: {expr}
    custom_extensions:
      - vendor_name: REFERENCE
        data: '{{"base_dataset": "orders", "allowed_dimensions": [{allowed}]}}'
'''


@pytest.fixture(scope="module")
def ctx() -> SemanticContextService:
    fields = "".join(
        f"      - name: orders_{n}\n        datatype: {t}\n        expression:\n          dialects:\n            - dialect: ANSI_SQL\n              expression: {n}\n"
        for n, t in _FIELDS.items()
    )
    allowed = ",".join(f'"orders_{n}"' for n in _FIELDS)
    root = pathlib.Path(tempfile.mkdtemp()) / "rt"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "reference_core.ossie.yaml").write_text(
        'version: "0.2.0.dev0"\nname: orders\ndescription: x\ndatasets:\n  - name: orders\n    source: \'"hive"."default"."fulfillment_orders"\'\n    primary_key: [order_id]\n    fields:\n'
        + fields
        + "metrics:\n"
        + _metric("total_orders", "Total number of orders.", '["orders", "order count"]', "COUNT(order_id)", allowed)
        + _metric("total_order_value_idr", "Total order value in IDR.", '["order value", "nilai order", "revenue", "sales value"]', "SUM(order_value)", allowed)
    )
    (ossie / "reference_governance.yaml").write_text('unknown_metric_question: "Which?"\n')
    (ossie / "golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


@pytest.mark.parametrize(
    "question",
    ["berapa total order di bulan maret 2026 ini ?", "berapa total orders di bulan maret 2026 ini ?", "Total order in March 2026", "Total orders in March 2026"],
)
def test_order_and_orders_both_mean_the_count(ctx: SemanticContextService, question: str) -> None:
    assert ctx.resolve(question)["metric"] == "total_orders"


@pytest.mark.parametrize("question", ["berapa nilai order bulan maret 2026", "What is the total order value?"])
def test_the_value_wording_still_means_the_value(ctx: SemanticContextService, question: str) -> None:
    assert ctx.resolve(question)["metric"] == "total_order_value_idr"
