from __future__ import annotations

import pytest

from app.ask_data.drill_across import align_dimensions, find_metrics, merge_results
from tests.test_credit_risk_characterization import CASES, _build


@pytest.fixture(scope="module")
def ctx():
    return _build()


def test_two_named_metrics_are_found_in_question_order(ctx) -> None:
    found = find_metrics("Show the average decision time and the approval rate by region", ctx.registry)
    assert found == ["avg_decision_time_hours", "approval_rate"]


def test_synonyms_count_and_one_metric_questions_stay_single(ctx) -> None:
    assert find_metrics("Compare the approval percentage with the number of applications by channel", ctx.registry) == [
        "approval_rate",
        "total_applications",
    ]
    for question, *_ in CASES:  # the questions verified on real data must not turn into drill-across
        assert len(find_metrics(question, ctx.registry)) < 2, question


def test_dimensions_are_aligned_per_metric(ctx) -> None:
    metrics = ["approval_rate", "avg_decision_time_hours"]
    definitions = {m: ctx.metric_definition(m) for m in metrics}
    queries = align_dimensions("approval rate and average decision time by region and channel", metrics, ctx.registry, definitions)
    assert [q.dimensions for q in queries] == [
        ["credit_applications_region_name", "credit_applications_application_channel"]
    ] * 2


def test_merge_joins_on_dimension_values_and_keeps_unmatched_groups() -> None:
    first = {
        "columns": ["region", "metric_value"],
        "rows": [{"region": "Bali", "metric_value": 67.8}, {"region": "Jawa Barat", "metric_value": 65.2}],
        "execution_ms": 5,
    }
    second = {
        "columns": ["lq_region", "metric_value"],
        "rows": [{"lq_region": "Jawa Barat", "metric_value": 7.4}, {"lq_region": "Aceh", "metric_value": 6.0}],
        "execution_ms": 7,
    }
    merged = merge_results([first, second], ["approval_rate", "delinquency_rate"])
    assert merged["columns"] == ["region", "metric_value", "delinquency_rate"]
    assert merged["rows"] == [
        {"region": "Bali", "metric_value": 67.8, "delinquency_rate": None},
        {"region": "Jawa Barat", "metric_value": 65.2, "delinquency_rate": 7.4},
        {"region": "Aceh", "metric_value": None, "delinquency_rate": 6.0},
    ]
    assert merged["row_count"] == 3 and merged["execution_ms"] == 12


def test_a_single_group_without_dimensions_merges_into_one_row() -> None:
    merged = merge_results(
        [{"columns": ["metric_value"], "rows": [{"metric_value": 1}]}, {"columns": ["metric_value"], "rows": [{"metric_value": 2}]}],
        ["a", "b"],
    )
    assert merged["rows"] == [{"metric_value": 1, "b": 2}]


# ---- two datasets in one model: approval (applications) and delinquency (loans) --------------------------------
import asyncio
import pathlib
import tempfile

from app.ask_data import drill_across as da
from app.ask_data import value_filters as vf
from app.semantic.context import SemanticContextService


def _fields(dataset: str, columns: dict[str, str]) -> str:
    out = ""
    for name, dt in columns.items():
        out += (
            f"      - name: {dataset}_{name}\n        datatype: {dt}\n        expression:\n          dialects:\n"
            f"            - dialect: ANSI_SQL\n              expression: {name}\n"
        )
        if dt == "Date":
            out += "        dimension:\n          is_time: true\n"
    return out


def _metric(name, dataset, columns, expr, synonyms):
    allowed = ",".join(f'"{dataset}_{c}"' for c in columns)
    return f"""  - name: {name}
    description: "{name}"
    ai_context:
      synonyms: {synonyms}
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: {expr}
    custom_extensions:
      - vendor_name: REFERENCE
        data: '{{"base_dataset": "{dataset}", "allowed_dimensions": [{allowed}]}}'
"""


def _two_dataset_ctx() -> SemanticContextService:
    apps = {"application_id": "String", "application_date": "Date", "region_name": "String", "application_channel": "String", "decision_status": "String"}
    loans = {"loan_id": "String", "assessment_date": "Date", "region_name": "String", "origination_channel": "String", "delinquency_flag": "Boolean"}
    root = pathlib.Path(tempfile.mkdtemp()) / "rt"
    (root / "ossie").mkdir(parents=True)
    (root / "ossie" / "reference_core.ossie.yaml").write_text(
        f'''version: "0.2.0.dev0"
name: credit
description: credit
datasets:
  - name: credit_applications
    source: '"hive"."default"."credit_applications"'
    primary_key: [application_id]
    fields:
{_fields("credit_applications", apps)}  - name: loan_quality
    source: '"hive"."default"."loan_quality"'
    primary_key: [loan_id]
    fields:
{_fields("loan_quality", loans)}metrics:
{_metric("approval_rate", "credit_applications", apps, "COUNT(CASE WHEN decision_status = 'Approved' THEN 1 END) * 100.0 / COUNT(application_id)", ["approval rate"])}{_metric("delinquency_rate", "loan_quality", loans, "COUNT(CASE WHEN delinquency_flag THEN 1 END) * 100.0 / COUNT(loan_id)", ["delinquency rate"])}'''
    )
    (root / "ossie" / "reference_governance.yaml").write_text('unknown_metric_question: "Which?"\n')
    (root / "ossie" / "golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


SOURCES = {"credit_applications": '"hive"."default"."credit_applications"', "loan_quality": '"hive"."default"."loan_quality"'}


class _Executor:
    async def execute(self, sql, state):
        if "DISTINCT" in sql and "region_name" in sql:
            return {"rows": [{"v": v} for v in ["Bali", "Jawa Barat"]]}
        return {"rows": []}


def test_two_datasets_are_planned_as_two_governed_queries() -> None:
    vf.clear_cache()
    ctx = _two_dataset_ctx()
    question = "Show the approval rate and the delinquency rate by region for Jawa Barat"
    planned = asyncio.run(
        da.plan_queries(
            question=question,
            primary_metric="approval_rate",
            semantic_context=ctx,
            qualified_sources=SOURCES,
            executor=_Executor(),
            state={},
        )
    )
    assert planned is not None
    queries, notes = planned
    assert [q.metric for q in queries] == ["approval_rate", "delinquency_rate"]
    assert "FROM \"hive\".\"default\".\"credit_applications\"" in queries[0].sql
    assert "FROM \"hive\".\"default\".\"loan_quality\"" in queries[1].sql
    assert all("GROUP BY d.region_name" in q.sql for q in queries)
    assert all("d.region_name = 'Jawa Barat'" in q.sql for q in queries)  # the value filter reaches both datasets
    assert notes == ["credit_applications_region_name = Jawa Barat"] or any("Jawa Barat" in n for n in notes)


def test_a_single_metric_question_is_not_drilled() -> None:
    ctx = _two_dataset_ctx()
    planned = asyncio.run(
        da.plan_queries(
            question="What is the approval rate by region?",
            primary_metric="approval_rate",
            semantic_context=ctx,
            qualified_sources=SOURCES,
            executor=_Executor(),
            state={},
        )
    )
    assert planned is None


def test_a_dataset_without_a_connector_source_falls_back_to_single_metric() -> None:
    ctx = _two_dataset_ctx()
    planned = asyncio.run(
        da.plan_queries(
            question="Approval rate and delinquency rate by region",
            primary_metric="approval_rate",
            semantic_context=ctx,
            qualified_sources={"credit_applications": SOURCES["credit_applications"]},
            executor=_Executor(),
            state={},
        )
    )
    assert planned is None
