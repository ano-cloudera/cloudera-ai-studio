from __future__ import annotations

import asyncio

import pytest

from app.ask_data import value_filters as vf
from tests.test_credit_risk_characterization import _build


@pytest.fixture(autouse=True)
def _fresh_cache():
    vf.clear_cache()
    yield
    vf.clear_cache()


CATALOG = {
    "region_name": ["Bali", "DKI Jakarta", "Jawa Barat", "Jawa Tengah", "Jawa Timur", "Sumatera Utara"],
    "application_channel": ["Branch", "Digital", "Partner"],
    "customer_segment": ["Priority", "Retail", "SME"],
}


def test_values_named_in_the_question_become_filters() -> None:
    found = vf.match_values("What share of approvals in Jawa Barat Digital were policy exceptions?", CATALOG)
    assert found == {"region_name": ["Jawa Barat"], "application_channel": ["Digital"]}


def test_matching_is_whole_word_and_case_insensitive() -> None:
    assert vf.match_values("digital transformation of retail banking", CATALOG) == {
        "application_channel": ["Digital"],
        "customer_segment": ["Retail"],
    }
    assert vf.match_values("approval rate for digitalization programs", CATALOG) == {}


def test_two_values_of_one_dimension_form_an_in_list() -> None:
    found = vf.match_values("Compare Bali and Jawa Timur", CATALOG)
    flt = vf.ValueFilter("region_name", "d.region_name", tuple(found["region_name"]))
    assert flt.predicate() == "d.region_name IN ('Bali', 'Jawa Timur')"


def test_questions_without_values_and_ambiguous_values_add_nothing() -> None:
    assert vf.match_values("What is the approval rate by region?", CATALOG) == {}
    assert vf.match_values("Show Premium", {"a": ["Premium"], "b": ["Premium"]}) == {}


def test_quotes_are_escaped() -> None:
    assert vf.ValueFilter("c", "d.c", ("O'Brien",)).predicate() == "d.c = 'O''Brien'"


class FakeExecutor:
    def __init__(self, values):
        self.values = values
        self.sql: list[str] = []

    async def execute(self, sql, state):
        self.sql.append(sql)
        for column, vals in self.values.items():
            if f"d.{column} " in sql:
                return {"rows": [{"v": v} for v in vals]}
        return {"rows": []}


def _resolve(ctx, question, executor):
    definition = ctx.metric_definition("approval_rate")
    return asyncio.run(
        vf.resolve_value_filters(
            question=question,
            dataset_name="credit_applications",
            metric_expression=definition["expression"],
            allowed_dimensions=set(definition["allowed_dimensions"]),
            from_source='"hive"."default"."credit_applications"',
            semantic_context=ctx,
            executor=executor,
            state={},
        )
    )


def test_values_come_from_the_data_and_are_cached() -> None:
    ctx = _build()
    executor = FakeExecutor(
        {"region_name": CATALOG["region_name"], "application_channel": CATALOG["application_channel"], "customer_segment": CATALOG["customer_segment"]}
    )
    filters = _resolve(ctx, "Approval rate for Jawa Barat Digital applicants", executor)
    assert {f.dimension: f.values for f in filters} == {
        "credit_applications_region_name": ("Jawa Barat",),
        "credit_applications_application_channel": ("Digital",),
    }
    queried = len(executor.sql)
    assert queried >= 3
    _resolve(ctx, "Approval rate for Bali", executor)
    assert len(executor.sql) == queried  # second question served from the cache
    # Columns the metric formula uses or identifiers are never looked up.
    assert not any("decision_status" in s or "application_id" in s or "policy_exception_flag" in s for s in executor.sql)


def test_a_failing_lookup_never_breaks_the_question() -> None:
    class Boom:
        async def execute(self, sql, state):
            raise RuntimeError("down")

    assert _resolve(_build(), "Approval rate for Jawa Barat", Boom()) == []


def test_the_filter_lands_in_the_governed_sql() -> None:
    ctx = _build()
    question = "What is the average decision time for Jawa Barat Digital from June to August 2026?"
    resolution = ctx.resolve(question)
    flt = vf.ValueFilter("credit_applications_region_name", "d.region_name", ("Jawa Barat",))
    sql = ctx.compile_governed(
        resolution["metric"], question, resolution["dimensions"], extra_predicates=[flt.predicate()]
    )
    assert "d.region_name = 'Jawa Barat'" in sql and "DATE '2026-06-01'" in sql


def test_a_clear_typo_is_applied_and_reported() -> None:
    from app.ask_data.value_filters import fuzzy_matches, match_values

    catalog = {"region": ["Sumatera Utara", "Sumatera Barat", "Jawa Timur", "Kalimantan Timur"]}
    question = "Bisa bantu compare data late delivery di stumatra udtara antara maret dan juni"
    found = fuzzy_matches(question, catalog, match_values(question, catalog))
    assert [(m.heard, m.values, m.applied) for m in found] == [("stumatra udtara", ("Sumatera Utara",), True)]
    assert [m.values for m in fuzzy_matches("late rate jawa tmur", catalog, {})] == [("Jawa Timur",)]


def test_a_tied_or_weak_match_is_only_a_question() -> None:
    from app.ask_data.value_filters import fuzzy_matches

    catalog = {"region": ["Sumatera Utara", "Sumatera Barat", "Jawa Timur"]}
    found = fuzzy_matches("late rate di sumatera", catalog, {})
    assert len(found) == 1 and not found[0].applied
    assert set(found[0].values) == {"Sumatera Utara", "Sumatera Barat"}


def test_ordinary_words_and_exact_matches_are_not_second_guessed() -> None:
    from app.ask_data.value_filters import fuzzy_matches, match_values

    catalog = {"region": ["Sumatera Utara", "Jawa Timur"], "carrier": ["NusaCargo", "KilatKirim"]}
    question = "What is the late delivery rate for Jawa Timur by carrier in March?"
    assert fuzzy_matches(question, catalog, match_values(question, catalog)) == []
    assert [m.values for m in fuzzy_matches("compare nusa cargo", catalog, {})] == [("NusaCargo",)]


def test_the_models_own_words_are_never_read_as_a_typo() -> None:
    from app.ask_data.value_filters import fuzzy_matches, match_values

    catalog = {"delivery_status": ["Delivered", "Failed", "Returned"], "region": ["Sumatera Utara"]}
    question = "Which region has the highest late delivery rate?"
    assert [m.values for m in fuzzy_matches(question, catalog, match_values(question, catalog))] == [("Delivered",)]  # the noise
    ignored = {"delivery", "shipments", "late"}
    assert fuzzy_matches(question, catalog, match_values(question, catalog), ignored) == []
    assert [m.values for m in fuzzy_matches("late rate di stumatra udtara", catalog, {}, ignored)] == [("Sumatera Utara",)]


def test_a_word_of_an_applied_typo_does_not_come_back_as_a_suggestion() -> None:
    from app.ask_data.value_filters import fuzzy_matches

    catalog = {"region": ["Kalimantan Timur", "Jawa Timur"]}
    found = fuzzy_matches("late delivery rate di kalimantn timur", catalog, {})
    assert [(m.values, m.applied) for m in found] == [(("Kalimantan Timur",), True)]
