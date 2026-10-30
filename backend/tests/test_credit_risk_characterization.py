"""Characterization of the Ask Data answers verified on the credit-risk demo.

These lock the metric, dimensions, period and ordering the governed path produces for the questions that were
checked against the source data, so legacy-domain code can be removed without changing a correct answer.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.ask_data.validation import validate_ask_data_sql
from app.semantic.context import SemanticContextService

DIMS = [
    "application_id", "application_date", "region_name", "customer_segment", "application_channel",
    "product_category", "decision_status", "policy_exception_flag", "decision_time_hours",
]
NUMERIC = {"decision_time_hours": "Number"}
ALLOWED = ",".join(f'"credit_applications_{d}"' for d in DIMS)

METRICS = [
    ("approval_rate", "Share of approved applications (0-100).",
     "COUNT(CASE WHEN decision_status = 'Approved' THEN 1 END) * 100.0 / COUNT(application_id)",
     ["approval percentage", "approval ratio"]),
    ("total_applications", "Number of credit applications.", "COUNT(application_id)", ["number of applications"]),
    ("avg_decision_time_hours", "Average hours from application to decision.", "AVG(decision_time_hours)",
     ["average decision time", "decision time", "time to decision"]),
    ("policy_exception_approvals", "Applications approved by policy exception.",
     "COUNT(CASE WHEN decision_status = 'Approved' AND policy_exception_flag THEN 1 END)",
     ["approved by policy exception", "policy exception approvals"]),
]


def _fields() -> str:
    out = ""
    for d in DIMS:
        if d == "application_date":
            dt = "Date"
        elif d.endswith("flag"):
            dt = "Boolean"
        elif d in NUMERIC:
            dt = "Number"
        else:
            dt = "String"
        out += (
            f"      - name: credit_applications_{d}\n        datatype: {dt}\n        expression:\n"
            f"          dialects:\n            - dialect: ANSI_SQL\n              expression: {d}\n"
        )
        if d == "application_date":
            out += "        dimension:\n          is_time: true\n"
    return out


def _metric(name: str, desc: str, expr: str, synonyms: list[str]) -> str:
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
        data: '{{"base_dataset": "credit_applications", "allowed_dimensions": [{ALLOWED}]}}'
"""


def _build() -> SemanticContextService:
    root = pathlib.Path(tempfile.mkdtemp()) / "rt"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "reference_core.ossie.yaml").write_text(
        f'''version: "0.2.0.dev0"
name: credit
description: credit risk
datasets:
  - name: credit_applications
    source: '"hive"."default"."credit_applications"'
    primary_key: [application_id]
    fields:
{_fields()}metrics:
{"".join(_metric(*m) for m in METRICS)}'''
    )
    (ossie / "reference_governance.yaml").write_text('unknown_metric_question: "Which metric do you mean?"\n')
    (ossie / "golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


@pytest.fixture(scope="module")
def ctx() -> SemanticContextService:
    return _build()


_STATE = {
    "datasource_context": {
        "legacy_fallback": False,
        "connector_id": "00000000-0000-0000-0000-000000000001",
        "connector_type": "trino",
        "connector_name": "t",
        "dialect": "trino",
        "semantic_version_id": "00000000-0000-0000-0000-000000000002",
        "semantic_entity_keys": ["credit_applications"],
        "qualified_sources": {"credit_applications": '"hive"."default"."credit_applications"'},
        "allowed_physical_tables": ["hive.default.credit_applications"],
    }
}

CASES = [
    # question, metric, group-by dimensions, SQL fragments that must appear
    ("What is the approval rate by region?", "approval_rate", ["region_name"], ["GROUP BY d.region_name"]),
    (
        "Which region has the lowest approval rate from June to August 2026?",
        "approval_rate", ["region_name"],
        ["GROUP BY d.region_name", "ORDER BY metric_value ASC", "DATE '2026-06-01'", "DATE '2026-09-01'"],
    ),
    (
        "Compare the approval rate by region and channel from June to August 2026",
        "approval_rate", ["region_name", "application_channel"],
        ["GROUP BY d.region_name, d.application_channel", "DATE '2026-06-01'", "DATE '2026-09-01'"],
    ),
    (
        "How many applications were approved by policy exception?",
        "policy_exception_approvals", [],
        ["policy_exception_flag"],
    ),
    (
        "What is the average decision time by channel?",
        "avg_decision_time_hours", ["application_channel"],
        ["AVG(decision_time_hours)", "GROUP BY d.application_channel"],
    ),
    ("What is the approval rate by customer segment?", "approval_rate", ["customer_segment"], ["GROUP BY d.customer_segment"]),
]


@pytest.mark.parametrize(("question", "metric", "dims", "fragments"), CASES, ids=[c[0][:40] for c in CASES])
def test_verified_questions_resolve_to_the_right_metric_and_query(ctx, question, metric, dims, fragments) -> None:
    resolution = ctx.resolve(question)
    assert resolution["status"] == "resolved", resolution
    assert resolution["metric"] == metric
    assert resolution["dimensions"] == [f"credit_applications_{d}" for d in dims]
    sql = ctx.compile_governed(resolution["metric"], question, resolution["dimensions"])
    for fragment in fragments:
        assert fragment in sql, (fragment, sql)
    assert validate_ask_data_sql(sql, ctx, state={**_STATE, "semantic_resolution": resolution}).valid


def test_a_single_kpi_has_no_grouping(ctx) -> None:
    question = "How many credit applications do we have in total?"
    resolution = ctx.resolve(question)
    assert resolution["metric"] == "total_applications"
    assert "GROUP BY" not in ctx.compile_governed(resolution["metric"], question, resolution["dimensions"])


def test_follow_ups_keep_the_metric_and_follow_the_named_dimension(ctx) -> None:
    session = {"last_metric": "approval_rate", "last_question": "What is the approval rate by region?"}
    by_channel = ctx.resolve("Break it down by channel", session_analysis_context=session)
    assert by_channel["metric"] == "approval_rate"
    assert by_channel["dimensions"] == ["credit_applications_application_channel"]
    assert ctx.resolve("Break it down", session_analysis_context=session)["status"] == "needs_clarification"


def test_an_explicit_new_metric_beats_the_previous_turn(ctx) -> None:
    session = {"last_metric": "approval_rate", "last_question": "What is the approval rate by region?"}
    resolution = ctx.resolve("What is the average decision time by channel?", session_analysis_context=session)
    assert resolution["metric"] == "avg_decision_time_hours"


@pytest.mark.parametrize("question", ["What is the weather in Jakarta tomorrow?", "Who won the football match?"])
def test_unrelated_questions_are_not_forced_onto_a_metric(ctx, question) -> None:
    assert ctx.resolve(question)["status"] != "resolved"
