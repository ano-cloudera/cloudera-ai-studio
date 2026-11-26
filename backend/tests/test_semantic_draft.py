"""Drafting a semantic model from the data: the profile, the checks that stand between the AI model and the reviewer, and the whole
draft on a real (SQLite) database with a scripted model."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from app.connectors.metadata import ColumnInfo
from app.connectors.type_normalization import normalize_data_type
from app.semantic_registry.semantic_draft import (
    DraftDimension,
    DraftMetric,
    DraftRelationship,
    DraftTable,
    DraftTerm,
    HeadlinePick,
    LinksDraft,
    TableDraft,
    aggregation_of,
    clean_synonyms,
    draft_model,
    expression_problem,
    slug,
)
from app.semantic_registry.table_profile import check_join, profile_table


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(
        """
        CREATE TABLE customers (customer_code TEXT, segment TEXT, province TEXT);
        CREATE TABLE orders (order_id INTEGER, customer_code TEXT, status TEXT, amount REAL, duration_minutes INTEGER, order_date TEXT, notes TEXT);
        """
    )
    customers = [(f"C{i:03d}", "Retail" if i % 3 else "Industry", ["Jawa Barat", "Bali", "Papua"][i % 3]) for i in range(30)]
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
    statuses = ["Delivered", "Delivered", "Late", "In_Transit"]
    orders = [
        (i, f"C{i % 30:03d}", statuses[i % 4], 100.0 + i, 30 + i % 50, f"2026-0{1 + i % 9}-1{i % 9}", f"note {i}")
        for i in range(400)
    ]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", orders)

    def run(sql: str, max_rows: int):
        cur = conn.execute(sql)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchmany(max_rows)]

    run.queries = []  # type: ignore[attr-defined]
    return run


def _columns(*pairs: tuple[str, str]) -> list[ColumnInfo]:
    return [ColumnInfo(name=n, data_type=t, native_type=t, normalized_type=normalize_data_type(t)) for n, t in pairs]


ORDERS = _columns(("order_id", "bigint"), ("customer_code", "varchar"), ("status", "varchar"), ("amount", "double"),
                  ("duration_minutes", "integer"), ("order_date", "date"), ("notes", "varchar"), ("tags", "array(varchar)"))
CUSTOMERS = _columns(("customer_code", "varchar"), ("segment", "varchar"), ("province", "varchar"))


def _profile(run, table: str, columns):
    return profile_table(run, connector_type="trino", catalog=None, schema=None, table=table, table_sql=f'"{table}"', columns=columns)


def test_the_profile_reads_counts_ranges_and_the_common_values_from_the_data(db) -> None:
    profile = _profile(db, "orders", ORDERS)
    assert profile.row_count == 400 and profile.sample_rows == 400
    assert profile.skipped_columns == ["tags"]  # a nested type is left out
    status = profile.column("status")
    assert status.distinct == 3 and dict(status.top_values) == {"Delivered": 200, "Late": 100, "In_Transit": 100}
    assert profile.column("amount").minimum == 100.0 and profile.column("amount").maximum == 499.0
    assert profile.column("order_id").distinct == 400 and not profile.column("order_id").top_values  # many values: not listed
    assert profile.column("duration_minutes").top_values  # a number with few values (a code) is listed
    shown = profile.for_prompt()
    assert shown["columns"][2]["common_values"][0] == ["Delivered", 200] and shown["columns"][0]["filled_pct"] == 100.0


def test_a_failing_query_leaves_a_gap_not_an_error(db) -> None:
    def flaky(sql: str, max_rows: int):
        if "COUNT(*) AS row_count" in sql:
            raise RuntimeError("view too slow")
        return db(sql, max_rows)

    profile = _profile(flaky, "orders", ORDERS)
    assert profile.row_count is None and profile.sample_rows == 400 and profile.notes


@pytest.mark.parametrize(
    "expression,problem",
    [
        ("SUM(amount)", None),
        ("COUNT(CASE WHEN status = 'Late' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)", None),
        ("COUNT(CASE WHEN status IN ('Late', 'Delivered') THEN 1 END)", None),
        ("SUM(revenue)", "column the table does not have: revenue"),
        ("COUNT(CASE WHEN status = 'late' THEN 1 END)", "does not hold"),  # the value is 'Late'
        ("amount * 2", "does not aggregate"),
        ("SUM(amount) / (SELECT COUNT(*) FROM orders)", "query of its own"),
        ("SUM(amount) OVER ()", "window function"),
        ("SUM(amount", "could not be read"),
    ],
)
def test_a_metric_is_judged_from_its_sql_and_the_profile(db, expression, problem) -> None:
    found = expression_problem(expression, _profile(db, "orders", ORDERS))
    assert (found is None) if problem is None else (problem in (found or ""))


def test_a_value_filter_is_not_judged_when_the_profile_does_not_know_every_value(db) -> None:
    # notes has 400 values and only the top ten are known: a filter on an unseen note may still be right.
    assert expression_problem("COUNT(CASE WHEN notes = 'note 399' THEN 1 END)", _profile(db, "orders", ORDERS)) is None


def test_aggregation_names_a_single_call_only() -> None:
    assert aggregation_of("SUM(amount)") == "sum"
    assert aggregation_of("COUNT(DISTINCT customer_code)") == "count"  # the registry knows sum, avg, count, min, max
    assert aggregation_of("SUM(a) / SUM(b)") is None
    assert aggregation_of("COUNT(CASE WHEN s = 'x' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)") is None


def test_keys_are_readable_and_safe() -> None:
    assert slug("Late Rate (%)") == "late_rate"
    assert slug("2026 Revenue") == "x_2026_revenue"
    assert slug("Tingkat Keterlambatan (%)") == "tingkat_keterlambatan"


def test_a_shared_synonym_is_removed_from_both_items() -> None:
    items = [
        {"name": "Revenue", "synonyms": ["sales", "income", "Income"]},
        {"name": "Order count", "synonyms": ["sales", "orders", "revenue"]},
    ]
    assert clean_synonyms(items) == 3
    assert items[0]["synonyms"] == ["income"] and items[1]["synonyms"] == ["orders"]


def test_a_join_is_confirmed_by_the_values_it_links(db) -> None:
    good = check_join(db, connector_type="trino", from_table_sql='"orders"', from_column="customer_code", to_table_sql='"customers"', to_column="customer_code")
    bad = check_join(db, connector_type="trino", from_table_sql='"orders"', from_column="status", to_table_sql='"customers"', to_column="segment")
    assert good.checked == 30 and good.ratio == 1.0
    assert bad.checked == 3 and bad.matched == 0


class ScriptedModel:
    """Answers like the AI model would, with the mistakes a model makes."""

    def __init__(self, fail_tables: set[str] | None = None, headline: list[tuple[str, str]] | None = None) -> None:
        self.fail_tables = fail_tables or set()
        self.headline = headline or []
        self.calls: list[dict] = []

    async def generate_structured(self, messages, response_model, *, temperature, max_tokens):
        import json

        payload = json.loads(messages[1]["content"])
        self.calls.append(payload)
        if response_model is LinksDraft:
            return LinksDraft(
                relationships=[
                    DraftRelationship(from_table="orders", from_column="customer_code", to_table="customers", to_column="customer_code", description="Each order belongs to a customer."),
                    DraftRelationship(from_table="orders", from_column="status", to_table="customers", to_column="segment"),
                    DraftRelationship(from_table="orders", from_column="missing", to_table="customers", to_column="customer_code"),
                ],
                terms=[DraftTerm(term="In_Transit", definition="An order that has left but not arrived.", synonyms=["on the way"])],
                headline=[HeadlinePick(table=t, metric=m) for t, m in self.headline],
            )
        table = payload["table_profile"]["table"]
        if table in self.fail_tables:
            raise RuntimeError("model timed out")
        if table == "customers":
            return TableDraft(
                name="Customer",
                description="One row per customer.",
                primary_key="customer_code",
                dimensions=[DraftDimension(column="customer_code", name="Customer", kind="identifier"),
                            DraftDimension(column="segment", name="Segment", kind="category", synonyms=["customer type"]),
                            DraftDimension(column="province", name="Province", kind="place", synonyms=["region", "sales"])],
                metrics=[DraftMetric(name="Customers", expression="COUNT(DISTINCT customer_code)", unit="customers", better="up", synonyms=["number of customers"])],
                headline=["Customers"],
            )
        return TableDraft(
            name="Order",
            description="One row per order.",
            primary_key="order_id",
            dimensions=[
                DraftDimension(column="status", name="Status", kind="category", synonyms=["order status"]),
                DraftDimension(column="status", name="Status again", kind="category"),  # a second dimension on one column
                DraftDimension(column="order_date", name="Order Date", kind="time", synonyms=["date", "month"]),
                DraftDimension(column="region", name="Region"),  # no such column
                DraftDimension(column="customer_code", name="Customer", kind="identifier"),
            ],
            metrics=[
                DraftMetric(name="Revenue (USD)", expression="SUM(orders.amount)", unit="USD", better="up", synonyms=["sales", "revenue total"]),
                DraftMetric(name="Late Rate (%)", expression="COUNT(CASE WHEN status = 'Late' THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN status <> 'In_Transit' THEN 1 END), 0)", unit="percent", better="down"),
                DraftMetric(name="Average Duration (minutes)", expression="AVG(duration_minutes)", unit="minutes", better="down"),
                DraftMetric(name="Lost Revenue", expression="SUM(lost_amount)", unit="USD"),  # no such column
                DraftMetric(name="Cancelled Orders", expression="COUNT(CASE WHEN status = 'Cancelled' THEN 1 END)"),  # no such value
                DraftMetric(name="Distinct Approx", expression="APPROX_DISTINCT(customer_code)"),  # SQLite cannot run it
            ],
            headline=["Revenue (USD)", "Late Rate (%)"],
        )


def _tables(db) -> list[DraftTable]:
    return [
        DraftTable(key="orders", connection_id="c1", profile=_profile(db, "orders", ORDERS), run=db),
        DraftTable(key="customers", connection_id="c1", profile=_profile(db, "customers", CUSTOMERS), run=db),
    ]


def test_the_draft_offers_only_what_the_data_confirms(db) -> None:
    model = ScriptedModel()
    stages: list[str] = []
    result = asyncio.run(draft_model(model, _tables(db), language="id", context="Online shop", provider_label="test-model", progress=stages.append)).to_dict()

    assert result["provider"] == "test-model" and result["drafted"] is True
    assert model.calls[0]["language"] == "Bahasa Indonesia" and model.calls[0]["business_context"] == "Online shop"

    orders = next(e for e in result["entities"] if e["key"] == "orders")
    assert orders["source_type"] == "trino" and orders["primary_key"] == "order_id" and orders["evidence"]["row_count"] == 400
    assert {c["name"] for c in orders["metadata"]["physical_columns"]} >= {"amount", "status"}

    dims = {d["key"]: d for d in result["dimensions"]}
    assert set(dims) == {"status", "order_date", "customer_code", "customers_customer_code", "segment", "province"}  # one per column, none invented
    assert dims["customer_code"]["name"] == "Customer (Order)" and dims["customers_customer_code"]["name"] == "Customer (Customer)"
    assert dims["order_date"]["category"] == "TIME" and dims["province"]["category"] == "GEO"
    assert dims["status"]["evidence"]["examples"][0] == "Delivered"

    metrics = {m["key"]: m for m in result["metrics"]}
    assert set(metrics) == {"revenue", "late_rate", "average_duration", "customers"}
    assert metrics["revenue"]["expression"] == "SUM(amount)"  # the table prefix is removed
    assert metrics["revenue"]["evidence"] == {"value": pytest.approx(sum(100.0 + i for i in range(400))), "rows": 400, "whole_table": True}
    assert metrics["late_rate"]["evidence"]["value"] == pytest.approx(100 / 300 * 100)
    # No pick across tables: each table's first headline, in table order, makes one ranking.
    assert metrics["revenue"]["metadata"]["reference_extension"] == {"headline": 1, "better": "up"}
    assert metrics["customers"]["metadata"]["reference_extension"] == {"headline": 2, "better": "up"}
    assert metrics["late_rate"]["metadata"]["reference_extension"] == {"better": "down"}
    assert metrics["revenue"]["aggregation"] == "sum" and metrics["late_rate"]["aggregation"] is None

    dropped = {d["name"]: d["reason"] for d in result["dropped"]}
    assert "column the table does not have" in dropped["Lost Revenue"]
    assert "does not hold" in dropped["Cancelled Orders"]
    assert "did not run on the data" in dropped["Distinct Approx"]
    assert "no column region" in dropped["Region"]

    assert [r["join_expression"] for r in result["relationships"]] == ["orders.customer_code = customers.customer_code"]
    assert result["relationships"][0]["evidence"] == {"matched": 30, "checked": 30}
    assert any("does not confirm" in r for n, r in dropped.items() if "status" in n)
    assert any("does not exist" in r for n, r in dropped.items() if "missing" in n)

    assert result["glossary_suggestions"][0]["related_metric_keys"] == []
    # "sales" was given to Revenue and to Province: removed from both.
    assert "sales" not in metrics["revenue"]["synonyms"] and "sales" not in dims["province"]["synonyms"]
    assert stages[-1] == "Done" and any("Running every metric" in s for s in stages)


def test_a_table_the_model_cannot_draft_still_comes_in_without_stopping_the_others(db) -> None:
    result = asyncio.run(draft_model(ScriptedModel(fail_tables={"orders"}), _tables(db), provider_label="m")).to_dict()
    assert {e["key"] for e in result["entities"]} == {"orders", "customers"}
    assert {m["key"] for m in result["metrics"]} == {"customers"}
    assert any("could not draft orders" in n for n in result["notes"])


def test_the_headline_picked_across_tables_is_the_one_ranking(db) -> None:
    model = ScriptedModel(headline=[("customers", "Customers"), ("orders", "Late Rate (%)"), ("orders", "No Such Metric")])
    result = asyncio.run(draft_model(model, _tables(db), provider_label="m")).to_dict()
    ranks = {m["key"]: m["metadata"].get("reference_extension", {}).get("headline") for m in result["metrics"]}
    assert ranks == {"customers": 1, "late_rate": 2, "revenue": None, "average_duration": None}
    assert model.calls[-1]["tables"][0]["metrics"] == ["Revenue (USD)", "Late Rate (%)", "Average Duration (minutes)"]  # only what ran


def test_a_large_table_is_checked_on_the_sample(db, monkeypatch) -> None:
    from app.semantic_registry import semantic_draft

    monkeypatch.setattr(semantic_draft, "WHOLE_TABLE_ROWS", 100)
    result = asyncio.run(draft_model(ScriptedModel(), _tables(db), provider_label="m")).to_dict()
    revenue = next(m for m in result["metrics"] if m["key"] == "revenue")
    assert revenue["evidence"]["whole_table"] is False and revenue["evidence"]["rows"] == 400
