from pathlib import Path

from app.services.usage_store import UsageStore


def test_usage_store_record_and_totals(tmp_path: Path) -> None:
    store = UsageStore(tmp_path / "usage.sqlite")
    store.record(
        request_id="r1",
        session_id="s1",
        provider="gemini",
        model="gemini-test",
        strategy="governed",
        status="SUCCESS",
        prompt_tokens=100,
        completion_tokens=50,
        llm_calls=2,
    )
    totals = store.totals(days=7)
    assert totals["total_tokens"] == 150
    assert totals["llm_calls"] == 2
    assert totals["turns"] == 1
    events = store.list_events(days=7, limit=10)
    assert len(events) == 1
    assert events[0]["model"] == "gemini-test"


def test_prior_totals_are_the_stretch_of_the_same_length_just_before(tmp_path: Path) -> None:
    import sqlite3
    from datetime import datetime, timedelta, timezone

    from app.api.usage import _prior_totals

    store = UsageStore(tmp_path / "usage.sqlite")
    for request_id, tokens in (("now", 100), ("last_week", 40), ("long_ago", 900)):
        store.record(request_id=request_id, session_id="s", provider="p", model="m", strategy="governed", status="SUCCESS", prompt_tokens=tokens, completion_tokens=0, llm_calls=1)
    with sqlite3.connect(store.path) as connection:
        for request_id, days_ago in (("last_week", 10), ("long_ago", 30)):
            when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(microsecond=0).isoformat()
            connection.execute("UPDATE llm_usage_events SET created_at = ? WHERE request_id = ?", (when, request_id))
    current = store.totals(days=7)
    prior, length = _prior_totals(store, days=7, mtd=False, current=current)
    assert current["total_tokens"] == 100 and length == 7
    assert prior["total_tokens"] == 40 and prior["turns"] == 1  # the event 10 days ago, not the one 30 days ago


def test_a_month_to_date_window_is_the_same_for_totals_days_models_events_and_the_export(tmp_path: Path) -> None:
    import sqlite3
    from datetime import datetime, timezone

    store = UsageStore(tmp_path / "usage.sqlite")
    for request_id in ("this_month", "last_month"):
        store.record(request_id=request_id, session_id="s", provider="p", model="m", strategy="governed", status="SUCCESS", prompt_tokens=10, completion_tokens=0, llm_calls=1)
    now = datetime.now(timezone.utc)
    last_month_end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).replace(microsecond=0)
    before = (last_month_end.replace(day=1) - __import__("datetime").timedelta(hours=2)).isoformat()  # two hours before this month began
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE llm_usage_events SET created_at = ? WHERE request_id = 'last_month'", (before,))
    assert store.totals(mtd=True)["turns"] == 1
    assert [row["tokens"] for row in store.by_model(mtd=True)] == [10]
    assert sum(row["tokens"] for row in store.daily_totals(mtd=True)) == 10
    assert [e["request_id"] for e in store.list_events(mtd=True)] == ["this_month"]
    assert store.export_csv(mtd=True).count("this_month") == 1 and "last_month" not in store.export_csv(mtd=True)
    assert len(store.list_events(days=31)) == 2  # a rolling 31 days is not the month to date
