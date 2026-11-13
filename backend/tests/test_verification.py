from __future__ import annotations

from app.ask_data.verification import verify_answer, warning_messages

PCT = {"expression": "COUNT(x) * 100.0 / COUNT(y)", "unit_format": "percent"}
SQL_DATE = "SELECT 1 FROM t d WHERE d.ship_date >= DATE '2026-03-01' AND d.ship_date < DATE '2026-06-01'"


def _checks(question: str, sql: str = "SELECT 1 FROM t d", rows=None, drill=None, definition=None, truncated=False):
    return verify_answer(question=question, sql=sql, columns=["metric_value"], rows=rows if rows is not None else [{"metric_value": 5}], definition=definition, drill=drill, truncated=truncated)


def test_a_named_period_without_a_date_filter_is_flagged() -> None:
    bad = _checks("late rate from March to May 2026")
    assert [c.status for c in bad if c.name == "period"] == ["warning"]
    good = _checks("late rate from March to May 2026", SQL_DATE)
    assert [c.status for c in good if c.name == "period"] == ["ok"]


def test_a_monthly_question_needs_a_month_split() -> None:
    assert warning_messages(_checks("orders per month")) and "monthly" in warning_messages(_checks("orders per month"))[0]
    assert not warning_messages(_checks("orders per month", "SELECT DATE_TRUNC('month', CAST(d.x AS TIMESTAMP)) FROM t d"))


def test_a_percentage_is_flagged_only_when_no_percentage_could_take_that_value() -> None:
    # A quota attainment of 101.9% is real; 14,000% is a rate scaled twice.
    assert not warning_messages(_checks("quota attainment", rows=[{"metric_value": 101.9}], definition=PCT))
    assert warning_messages(_checks("late rate", rows=[{"metric_value": 14000}], definition=PCT))
    ok = _checks("late rate", rows=[{"metric_value": 23.1}], definition=PCT)
    assert [c.status for c in ok if c.name == "range"] == ["ok"]
    assert not _checks("orders", rows=[{"metric_value": 8000}], definition={"expression": "COUNT(x)"})


def test_an_ordinary_question_has_no_checks_and_truncation_is_flagged() -> None:
    assert _checks("which region is highest") == []
    assert warning_messages(_checks("which region is highest", truncated=True))
    periods = _checks("compare march to may with june to august", drill={"kind": "periods"})
    assert [c.name for c in periods] == ["period"] and periods[0].status == "ok"


def test_months_without_a_year_must_still_be_a_date_filter() -> None:
    question = "Bisa bantu compare data late delivery di sumatera utara antara maret dan juni"
    checks = verify_answer(question=question, sql="SELECT 1 FROM t", columns=[], rows=[], definition=None, drill=None)
    assert [c.status for c in checks if c.name == "period"] == ["warning"]
    assert "2026-03 to 2026-06" in checks[0].message

    dated = "SELECT 1 FROM t WHERE d.order_date >= DATE '2026-03-01' AND d.order_date < DATE '2026-07-01'"
    checks = verify_answer(question=question, sql=dated, columns=[], rows=[], definition=None, drill=None)
    assert [c.status for c in checks if c.name == "period"] == ["ok"]
