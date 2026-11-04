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
