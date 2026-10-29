"""Governed breakdowns and date ranges against a connector-style (credit) semantic registry."""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.ask_data.intent_satisfaction import (
    infer_dimensions_from_question,
    parse_period_range,
    requested_sort_direction,
    validate_registry_resolution,
)
from app.ask_data.validation import validate_ask_data_sql
from app.semantic.context import SemanticContextService


DIMS = ["application_id","application_date","region_name","customer_segment","application_channel","product_category","decision_status","policy_exception_flag"]
def fields():
    out=""
    for d in DIMS:
        dt = "Date" if d=="application_date" else ("Boolean" if d.endswith("flag") else "String")
        out += f"      - name: credit_applications_{d}\n        datatype: {dt}\n        expression:\n          dialects:\n            - dialect: ANSI_SQL\n              expression: {d}\n"
        if d=="application_date":
            out += "        dimension:\n          is_time: true\n"
    return out
ALLOWED = ",".join(f'"credit_applications_{d}"' for d in DIMS)
def metric(name, desc, expr, syn=()):
    ai = ("    ai_context:\n      synonyms: %s\n" % list(syn)) if syn else ""
    return f"""  - name: {name}
    description: "{desc}"
{ai}    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: {expr}
    custom_extensions:
      - vendor_name: TEMPO
        data: '{{"base_dataset": "credit_applications", "allowed_dimensions": [{ALLOWED}]}}'
"""
ms = metric("approval_rate","Share of approved applications (0-100).","COUNT(CASE WHEN decision_status = 'Approved' THEN 1 END) * 100.0 / COUNT(application_id)",["approval rate"]) + metric("total_applications","Total number of credit applications.","COUNT(application_id)",["total applications"])
def build():
    root = pathlib.Path(tempfile.mkdtemp())/"rt"; o=root/"ossie"; o.mkdir(parents=True)
    (o/"tempo_core.ossie.yaml").write_text(f'''version: "0.2.0.dev0"
name: credit
description: x
datasets:
  - name: credit_applications
    source: '"hive"."default"."credit_applications"'
    primary_key: [application_id]
    fields:
{fields()}metrics:
{ms}''')
    (o/"tempo_governance.yaml").write_text('unknown_metric_question: "Which?"\n')
    (o/"golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


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


@pytest.fixture(scope="module")
def ctx() -> SemanticContextService:
    return build()


@pytest.mark.parametrize(
    ("question", "start", "end"),
    [
        ("Compare the approval rate from June to August 2026.", "2026-06-01", "2026-09-01"),
        ("What is our delinquency rate in Q3 2026?", "2026-07-01", "2026-10-01"),
        ("Bandingkan approval rate selama Juni sampai Agustus 2026.", "2026-06-01", "2026-09-01"),
        ("total in May 2024", "2024-05-01", "2024-06-01"),
        ("approval rate in 2026", "2026-01-01", "2027-01-01"),
        ("from Dec 2025 to Feb 2026", "2025-12-01", "2026-03-01"),
    ],
)
def test_period_ranges(question: str, start: str, end: str) -> None:
    period = parse_period_range(question)
    assert period is not None
    assert (period.start.isoformat(), period.end.isoformat()) == (start, end)


def test_no_period_when_no_year_is_given() -> None:
    assert parse_period_range("What may happen next?") is None


def test_sort_direction() -> None:
    assert requested_sort_direction("Which region has the lowest approval rate?") == "ASC"
    assert requested_sort_direction("Which region has the highest approval rate?") == "DESC"


def test_region_dimension_is_recognised_by_name(ctx: SemanticContextService) -> None:
    definition = ctx.metric_definition("approval_rate")
    validation = validate_registry_resolution(
        "What is the approval rate by region?",
        {"status": "resolved", "metric": "approval_rate", "dimensions": []},
        definition=definition,
        registry=ctx.registry,
    )
    assert validation.intent_complete, validation.user_message


def test_breakdown_dimensions_follow_the_question(ctx: SemanticContextService) -> None:
    allowed = set(ctx.metric_definition("approval_rate")["allowed_dimensions"])

    def infer(question: str) -> list[str]:
        return infer_dimensions_from_question(question, allowed, dataset_name="credit_applications", registry=ctx.registry)

    assert infer("approval rate by region and channel from June to August 2026") == [
        "credit_applications_region_name",
        "credit_applications_application_channel",
    ]
    assert infer("What is the approval rate by customer segment?") == ["credit_applications_customer_segment"]
    assert infer("Which region has the lowest approval rate?") == ["credit_applications_region_name"]
    assert infer("Bandingkan approval rate per wilayah dan channel") == [
        "credit_applications_region_name",
        "credit_applications_application_channel",
    ]
    # A filter phrase is not a breakdown, and flags/ids are never grouped on.
    assert infer("How many applications were approved by policy exception?") == []
    assert infer("How many credit applications do we have in total?") == []


def test_region_channel_question_compiles_a_valid_trino_query(ctx: SemanticContextService) -> None:
    question = "Compare the approval rate by region and channel from June to August 2026."
    resolution = ctx.resolve(question)
    assert resolution["status"] == "resolved"
    sql = ctx.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "GROUP BY d.region_name, d.application_channel" in sql
    assert "DATE '2026-06-01'" in sql and "DATE '2026-09-01'" in sql
    assert validate_ask_data_sql(sql, ctx, state={**_STATE, "semantic_resolution": resolution}).valid


def test_lowest_region_orders_ascending(ctx: SemanticContextService) -> None:
    question = "Which region has the lowest approval rate from June to August 2026?"
    resolution = ctx.resolve(question)
    sql = ctx.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "GROUP BY d.region_name" in sql
    assert "ORDER BY metric_value ASC" in sql


_SESSION = {"last_metric": "total_applications", "last_question": "How many credit applications do we have in total?"}


def test_explicit_metric_wins_over_the_previous_turn(ctx: SemanticContextService) -> None:
    resolution = ctx.resolve("What is the approval rate by region?", session_analysis_context=_SESSION)
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "approval_rate"
    assert resolution["dimensions"] == ["credit_applications_region_name"]


def test_follow_up_breakdown_uses_the_named_dimension(ctx: SemanticContextService) -> None:
    resolution = ctx.resolve("Break it down by region", session_analysis_context=_SESSION)
    assert resolution["metric"] == "total_applications"
    assert resolution["matched_alias"] == "session_metric_continuation"
    assert resolution["dimensions"] == ["credit_applications_region_name"]


def test_follow_up_without_a_dimension_asks_instead_of_guessing(ctx: SemanticContextService) -> None:
    resolution = ctx.resolve("Break it down", session_analysis_context=_SESSION)
    assert resolution["status"] == "needs_clarification"
