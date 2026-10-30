"""The Ask Data resolver must work for any domain, not just credit risk.

A logistics-style model whose words ("stock", "dc", "retail", "amount", "channel") used to trip rules written for
older demo catalogs.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.semantic.context import SemanticContextService

DIMS = {"shipment_id": "String", "ship_date": "Date", "warehouse": "String", "sales_channel": "String", "retail_partner": "String"}
ALLOWED = ",".join(f'"shipments_{d}"' for d in DIMS)
METRICS = [
    ("on_time_rate", "Share of shipments delivered on time (0-100).",
     "COUNT(CASE WHEN delivered_on_time THEN 1 END) * 100.0 / COUNT(shipment_id)", ["on-time delivery rate"]),
    ("stock_on_hand", "Units currently in stock.", "SUM(units_in_stock)", ["inventory level", "stock level"]),
    ("shipment_amount", "Total shipment value.", "SUM(amount)", ["shipment value"]),
]


def _fields() -> str:
    out = ""
    for name, dt in DIMS.items():
        out += (
            f"      - name: shipments_{name}\n        datatype: {dt}\n        expression:\n          dialects:\n"
            f"            - dialect: ANSI_SQL\n              expression: {name}\n"
        )
        if dt == "Date":
            out += "        dimension:\n          is_time: true\n"
    return out


def _metric(name, desc, expr, synonyms) -> str:
    return f"""  - name: {name}
    description: "{desc}"
    ai_context:
      synonyms: {synonyms}
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: {expr}
    custom_extensions:
      - vendor_name: REFERENCE
        data: '{{"base_dataset": "shipments", "allowed_dimensions": [{ALLOWED}]}}'
"""


@pytest.fixture(scope="module")
def ctx() -> SemanticContextService:
    root = pathlib.Path(tempfile.mkdtemp()) / "rt"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "reference_core.ossie.yaml").write_text(
        f'''version: "0.2.0.dev0"
name: logistics
description: logistics
datasets:
  - name: shipments
    source: '"hive"."default"."shipments"'
    primary_key: [shipment_id]
    fields:
{_fields()}metrics:
{"".join(_metric(*m) for m in METRICS)}'''
    )
    (ossie / "reference_governance.yaml").write_text('unknown_metric_question: "Which metric do you mean?"\n')
    (ossie / "golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


@pytest.mark.parametrize(
    ("question", "metric", "dimension"),
    [
        ("What is the on-time delivery rate by warehouse?", "on_time_rate", "shipments_warehouse"),
        ("What is the stock level by warehouse?", "stock_on_hand", "shipments_warehouse"),
        ("Show the stock on hand for the retail partner Acme DC", "stock_on_hand", None),
        ("What is the total shipment value by channel?", "shipment_amount", "shipments_sales_channel"),
        ("Which channel has the lowest on-time rate?", "on_time_rate", "shipments_sales_channel"),
    ],
)
def test_domain_words_do_not_hijack_the_metric(ctx, question, metric, dimension) -> None:
    resolution = ctx.resolve(question)
    assert resolution["status"] == "resolved", resolution
    assert resolution["metric"] == metric
    if dimension:
        assert dimension in resolution["dimensions"]


def test_legacy_catalog_clarifications_never_appear_for_other_models(ctx) -> None:
    resolution = ctx.resolve("Compare the stock level at the dc versus the retail store, combined total stock")
    assert not str(resolution.get("reason") or "").startswith("sat_idm")
    assert all("sat_" not in str(o) for o in resolution.get("options") or [])
