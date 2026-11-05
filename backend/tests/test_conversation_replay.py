"""The ten questions of the field review, asked in one session against the sample data.

These are the failures found in production that no unit test with a fake data source could show: a question after a table
was read as 'the first row of that table', a typo made a follow-up with a column that does not exist, a period that nobody
wrote appeared. They run offline in about a second, so a change that brings one back is caught before it is deployed.
"""
from __future__ import annotations

import pytest

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("pytest_asyncio")

from replay_support import DATA, Replay  # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA / "orders.csv").exists(), reason="sample data not generated")


def value(response, column: str = "metric_value") -> float:
    return float(response.data.rows[0][column])


@pytest.mark.asyncio
async def test_the_session_from_the_field_review(monkeypatch) -> None:
    replay = Replay(monkeypatch)
    ask = replay.ask

    r = await ask("Total orders in March 2026")
    assert r.status == "SUCCESS" and value(r) == 1002
    assert "DATE '2026-03-01'" in r.queries_run[-1]

    r = await ask("How many orders do we get per month?")
    assert [int(row["metric_value"]) for row in r.data.rows] == [1014, 904, 1002, 963, 969, 1074, 1035, 1039]

    # Right after a table, a question that names its own month is a new question, not 'row 1 of that table'.
    r = await ask("berapa total order di bulan maret 2026 ini ?")
    assert r.status == "SUCCESS" and value(r) == 1002
    assert "fulfillment_orders_order_date =" not in r.queries_run[-1] and "T00:00:00" not in r.queries_run[-1]

    r = await ask("Which region has the highest late delivery rate?")
    assert r.status == "SUCCESS" and r.data.rows[0]["delivery_shipments_region_name"] == "Kalimantan Timur"
    assert value(r) == pytest.approx(23.15, abs=0.01)

    # A typo of the region that was on top of the previous table: one correct filter on the real column, not a follow-up.
    r = await ask("Berapa late delivery rate di kalimantn timur?")
    sql = r.queries_run[-1]
    assert r.status == "SUCCESS" and value(r) == pytest.approx(23.15, abs=0.01)
    assert sql.count("= 'Kalimantan Timur'") == 1 and "d.region_name = 'Kalimantan Timur'" in sql and "d.delivery_shipments_region_name" not in sql
    assert "2024" not in sql  # no period that the user never wrote

    r = await ask("Which carriers have a late rate above overall?")
    carriers = [row["delivery_shipments_carrier"] for row in r.data.rows]
    assert r.status == "SUCCESS" and set(carriers) == {"NusaCargo", "KilatKirim"} and "FastExpress" not in carriers

    r = await ask("Total orders from March to May")
    assert r.status == "SUCCESS" and value(r) == 2934 and "DATE '2026-06-01'" in r.queries_run[-1]

    r = await ask("Bandingkan late delivery rate Sumatera Utara bulan Maret dengan bulan Juni")
    assert r.status == "SUCCESS" and r.calculation is not None and r.calculation.kind == "comparison"
    march = replay.executor.scalar("SELECT 100.0 * COUNT(CASE WHEN is_late THEN 1 END) / COUNT(*) FROM delivery_shipments WHERE region_name = 'Sumatera Utara' AND ship_date >= DATE '2026-03-01' AND ship_date < DATE '2026-04-01'")
    june = replay.executor.scalar("SELECT 100.0 * COUNT(CASE WHEN is_late THEN 1 END) / COUNT(*) FROM delivery_shipments WHERE region_name = 'Sumatera Utara' AND ship_date >= DATE '2026-06-01' AND ship_date < DATE '2026-07-01'")
    row = r.data.rows[0]
    assert float(row["previous_value"]) == pytest.approx(march) and float(row["metric_value"]) == pytest.approx(june)
    assert all("d.region_name = 'Sumatera Utara'" in q for q in r.queries_run[-2:])

    r = await ask("Total orders in March 2020")
    assert r.status == "SUCCESS" and value(r) == 0


@pytest.mark.asyncio
async def test_a_question_that_really_points_at_the_last_result_still_follows_it(monkeypatch) -> None:
    replay = Replay(monkeypatch)
    await replay.ask("Which region has the highest late delivery rate?")
    r = await replay.ask("breakdown per carrier untuk yang tertinggi tadi")
    assert r.status in {"SUCCESS", "CLARIFICATION"}
    assert "d.delivery_shipments_region_name" not in r.queries_run[-1] if r.queries_run else True


@pytest.mark.asyncio
async def test_per_month_after_a_breakdown_groups_by_month_not_by_the_old_breakdown(monkeypatch) -> None:
    replay = Replay(monkeypatch)
    r = await replay.ask("Total orders by channel")
    assert r.status == "SUCCESS" and "fulfillment_orders_channel" in r.data.rows[0]
    r = await replay.ask("orders per month")
    assert r.status == "SUCCESS" and [int(row["metric_value"]) for row in r.data.rows] == [1014, 904, 1002, 963, 969, 1074, 1035, 1039]
    assert not any("channel" in column for column in r.data.columns)


@pytest.mark.asyncio
async def test_a_natural_breakdown_follow_up_continues_the_last_metric(monkeypatch) -> None:
    replay = Replay(monkeypatch)
    await replay.ask("Late delivery rate di Jawa Timur")
    r = await replay.ask("breakdown per carrier")
    assert r.status == "SUCCESS" and {row["delivery_shipments_carrier"] for row in r.data.rows} == {"NusaCargo", "KilatKirim", "FastExpress"}
    assert "material" not in r.queries_run[-1]  # not the sell-in drill of an older demo


# The conversation the way Cortex Analyst and Genie hold it: the model rewrites each follow-up into a full question,
# and that question is answered as if it were asked first. The scripted model writes what the prompt asks for.

LATE_SQL = (
    "SELECT carrier, 100.0 * COUNT(CASE WHEN is_late THEN 1 END) / COUNT(*) FROM delivery_shipments WHERE region_name = '{region}' "
    "GROUP BY carrier ORDER BY 2 DESC"
)


@pytest.mark.asyncio
async def test_a_follow_up_keeps_the_filter_of_the_previous_question(monkeypatch) -> None:
    from replay_support import ScriptedModel

    model = ScriptedModel(rewrites={"and per carrier?": "Late delivery rate per carrier in Jawa Timur"})
    replay = Replay(monkeypatch, model=model)
    await replay.ask("Late delivery rate in Jawa Timur")
    r = await replay.ask("and per carrier?")
    sql = r.queries_run[-1]
    assert r.status == "SUCCESS" and "d.region_name = 'Jawa Timur'" in sql and "GROUP BY d.carrier" in sql
    expected = {row[0]: row[1] for row in replay.executor.con.execute(LATE_SQL.format(region="Jawa Timur")).fetchall()}
    assert {row["delivery_shipments_carrier"]: pytest.approx(float(row["metric_value"])) for row in r.data.rows} == expected
    # What the model saw of the previous turn: how it was read, its metric and its first rows.
    previous = model.payloads[-1]["last_turn"]
    assert previous["metric"] and previous["first_rows"]


@pytest.mark.asyncio
async def test_that_region_is_the_region_on_top_of_the_previous_answer(monkeypatch) -> None:
    from replay_support import ScriptedModel

    model = ScriptedModel(rewrites={"show that region per carrier": "Late delivery rate per carrier in Kalimantan Timur"})
    replay = Replay(monkeypatch, model=model)
    first = await replay.ask("Which region has the highest late delivery rate?")
    assert first.data.rows[0]["delivery_shipments_region_name"] == "Kalimantan Timur"
    r = await replay.ask("show that region per carrier")
    assert model.payloads[-1]["last_turn"]["first_rows"][0]["delivery_shipments_region_name"] == "Kalimantan Timur"
    assert r.status == "SUCCESS" and "d.region_name = 'Kalimantan Timur'" in r.queries_run[-1]


@pytest.mark.asyncio
async def test_another_month_replaces_the_month_of_the_previous_question(monkeypatch) -> None:
    from replay_support import ScriptedModel

    replay = Replay(monkeypatch, model=ScriptedModel(rewrites={"kalau Juni?": "Total orders in June 2026"}))
    r = await replay.ask("Total orders in March 2026")
    assert value(r) == 1002
    r = await replay.ask("kalau Juni?")
    assert r.status == "SUCCESS" and value(r) == 1074 and "DATE '2026-06-01'" in r.queries_run[-1]


@pytest.mark.asyncio
async def test_a_fresh_question_is_answered_as_written_even_after_a_filtered_one(monkeypatch) -> None:
    from replay_support import ScriptedModel

    replay = Replay(monkeypatch, model=ScriptedModel())
    await replay.ask("Late delivery rate in Jawa Timur")
    r = await replay.ask("Late delivery rate per region")
    assert r.status == "SUCCESS" and "Jawa Timur'" not in r.queries_run[-1] and len(r.data.rows) > 1


@pytest.mark.asyncio
async def test_the_model_picks_the_metric_when_the_keywords_do_not(monkeypatch) -> None:
    from replay_support import ScriptedModel

    question = "berapa banyak paket yang kita kirim?"
    model = ScriptedModel(choices={question: "total_shipments"})
    replay = Replay(monkeypatch, model=model)
    r = await replay.ask(question)
    assert "MetricChoice" in model.calls
    assert r.status == "SUCCESS" and value(r) == replay.executor.scalar("SELECT COUNT(*) FROM delivery_shipments")


@pytest.mark.asyncio
async def test_a_metric_the_model_does_not_have_is_never_used(monkeypatch) -> None:
    from replay_support import ScriptedModel

    question = "berapa banyak paket yang kita kirim?"
    replay = Replay(monkeypatch, model=ScriptedModel(choices={question: "invented_metric"}))
    r = await replay.ask(question)
    assert r.status in {"CLARIFICATION", "clarification_required"} and not r.queries_run


@pytest.mark.asyncio
async def test_an_unsure_pick_offers_only_the_metrics_that_could_fit(monkeypatch) -> None:
    from replay_support import ScriptedModel

    question = "berapa banyak paket yang telat?"
    replay = Replay(monkeypatch, model=ScriptedModel(candidates={question: ["late_delivery_rate", "total_shipments"]}))
    r = await replay.ask(question)
    assert r.status == "clarification_required" and not r.queries_run
    assert [option.id for option in r.clarification.options] == ["late_delivery_rate", "total_shipments"]


@pytest.mark.asyncio
async def test_a_rewrite_that_takes_an_older_turn_is_not_used(monkeypatch) -> None:
    from replay_support import ScriptedModel

    # The model continues the late-rate turn instead of the orders turn just before.
    model = ScriptedModel(rewrites={"kalau Juni?": "Late delivery rate in Kalimantan Timur in June 2026"})
    replay = Replay(monkeypatch, model=model)
    await replay.ask("Late delivery rate in Kalimantan Timur per month")
    await replay.ask("Total orders in March 2026")
    r = await replay.ask("kalau Juni?")
    assert r.status == "SUCCESS" and "fulfillment_orders" in r.queries_run[-1] and "DATE '2026-06-01'" in r.queries_run[-1]
    assert value(r) == 1074


@pytest.mark.asyncio
async def test_a_follow_up_rewritten_in_other_words_keeps_the_last_metric(monkeypatch) -> None:
    from replay_support import ScriptedModel

    # Qwen wrote the metric in Indonesian, which no alias matches.
    model = ScriptedModel(rewrites={"kalau per carrier?": "tingkat keterlambatan pengiriman per carrier di Jawa Timur"})
    replay = Replay(monkeypatch, model=model)
    await replay.ask("Late delivery rate di Jawa Timur")
    r = await replay.ask("kalau per carrier?")
    sql = r.queries_run[-1]
    assert r.status == "SUCCESS" and "is_late" in sql and "d.region_name = 'Jawa Timur'" in sql and "GROUP BY d.carrier" in sql


@pytest.mark.asyncio
async def test_compare_with_one_month_compares_it_with_the_month_just_asked(monkeypatch) -> None:
    from replay_support import ScriptedModel

    replay = Replay(monkeypatch, model=ScriptedModel())  # the model does not rewrite anything
    r = await replay.ask("kalau bulan juni berapa total orders?")
    assert value(r) == 1074 and "GROUP BY" not in r.queries_run[-1]  # one month named, not a monthly breakdown
    r = await replay.ask("bisa bandingkan dengan bulan mei ?")
    assert r.status == "SUCCESS" and r.calculation is not None and r.calculation.kind == "comparison"
    row = r.data.rows[0]
    assert {float(row["previous_value"]), float(row["metric_value"])} == {969.0, 1074.0}


@pytest.mark.asyncio
async def test_small_talk_after_data_questions_is_a_conversation_not_a_metric_choice(monkeypatch) -> None:
    from replay_support import ScriptedModel

    replay = Replay(monkeypatch, model=ScriptedModel())
    await replay.ask("Total orders in March 2026")
    r = await replay.ask("kamu sebenernya bisa apa sih ?")
    assert r.status == "SUCCESS" and r.strategy == "conversational" and not r.queries_run
