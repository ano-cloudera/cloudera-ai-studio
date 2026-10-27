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
