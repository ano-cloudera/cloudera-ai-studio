"""The answer cache: what is kept, when it is served, and that it survives a restart."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.ask_data.answer_cache import STALE_LIMIT_SECONDS, AnswerCache
from app.core.models import AnalysisOutput, AskDataRequest, AskDataResponse, QueryData, Timings
from tests.replay_support import Replay, WorstCaseModel


def _response(status: str = "SUCCESS", strategy: str = "governed") -> AskDataResponse:
    answer = AnalysisOutput(direct_answer="16,07%", executive_summary="", insights=[], business_implications=[], caveats=[], data_reference="x")
    return AskDataResponse(request_id="r", session_id="s", status=status, provider="qwen", model="m", strategy=strategy, answer=answer, data=QueryData(), chart_spec=None, timings=Timings())  # type: ignore[arg-type]


def test_the_key_reads_the_question_not_its_spacing_or_case_and_separates_scopes() -> None:
    scope = {"semantic": "v3", "llm": "qwen/m"}
    assert AnswerCache.key("Berapa  tingkat keterlambatan?", scope) == AnswerCache.key("berapa tingkat keterlambatan", scope)
    assert AnswerCache.key("q", scope) != AnswerCache.key("q", {**scope, "semantic": "v4"})


def test_only_successful_data_answers_are_kept(tmp_path) -> None:
    cache = AnswerCache(tmp_path, mode="first")
    cache.put("a", _response())
    cache.put("b", _response(status="ERROR"))
    cache.put("c", _response(strategy="conversational"))
    assert cache.recent("a") and cache.recent("b") is None and cache.recent("c") is None


def test_fallback_mode_never_serves_a_repeat_only_a_stand_in(tmp_path) -> None:
    cache = AnswerCache(tmp_path, mode="fallback")
    cache.put("a", _response())
    assert cache.recent("a") is None and cache.stand_in("a") is not None
    off = AnswerCache(tmp_path / "off", mode="off")
    off.put("a", _response())
    assert off.stand_in("a") is None and not off.enabled


def test_a_repeat_must_be_fresh_but_a_stand_in_may_be_older(tmp_path) -> None:
    cache = AnswerCache(tmp_path, mode="first", ttl_seconds=60)
    cache.put("a", _response())
    value = cache._get("a")
    value["stored_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    cache._store.set("a", value)
    assert cache.recent("a") is None and cache.stand_in("a") is not None
    value["stored_at"] = (datetime.now(timezone.utc) - timedelta(seconds=STALE_LIMIT_SECONDS + 60)).isoformat()
    cache._store.set("a", value)
    assert cache.stand_in("a") is None


def test_the_cache_survives_a_restart(tmp_path) -> None:
    AnswerCache(tmp_path, mode="first").put("a", _response())
    assert AnswerCache(tmp_path, mode="first").recent("a")["response"]["answer"]["direct_answer"] == "16,07%"


# --- end to end through the real ChatService and workflow, on the sample data -------------------------------------------

QUESTION = "What is the late delivery rate by carrier?"


def _ask(replay: Replay, session: str):
    request = AskDataRequest(session_id=session, question=QUESTION, provider="qwen", model="m")
    return asyncio.run(replay.service.run(request))


@pytest.fixture()
def replay(monkeypatch):
    from app.ask_data import answer_context, value_filters

    yield Replay(monkeypatch, WorstCaseModel())
    # The data range and the dimension values are cached per source in the process; leave them as other tests expect them.
    answer_context._COVERAGE.clear()
    value_filters.clear_cache()


def test_first_mode_answers_a_repeated_question_from_the_cache_without_querying(replay, tmp_path) -> None:
    replay.service.answer_cache = AnswerCache(tmp_path, mode="first")
    live = _ask(replay, "s1")
    assert live.status == "SUCCESS" and live.cached_at is None
    queried = len(replay.executor.queries)
    again = _ask(replay, "s2")
    assert again.status == "SUCCESS" and again.cache_reason == "repeat" and again.cached_at
    assert len(replay.executor.queries) == queried  # nothing was asked of the data source
    assert again.data.rows == live.data.rows and again.session_id == "s2"
    assert replay.service.history.load("s2")[-1]["session_frame"]  # a follow-up can continue it


def test_fallback_mode_stands_in_when_the_data_source_fails(replay, tmp_path) -> None:
    replay.service.answer_cache = AnswerCache(tmp_path, mode="fallback")
    live = _ask(replay, "s1")
    assert live.status == "SUCCESS"

    def down(sql, state):
        raise RuntimeError("metastore-service:9083: SocketTimeoutException: Read timed out")

    replay.executor.execute = down
    stood = _ask(replay, "s2")
    assert stood.status == "SUCCESS" and stood.cache_reason == "data_source_unavailable"
    assert any("cannot be reached" in c or "tidak bisa dijangkau" in c for c in stood.answer.caveats)
    assert stood.data.rows == live.data.rows


def test_fallback_mode_still_answers_live_when_the_data_source_is_up(replay, tmp_path) -> None:
    replay.service.answer_cache = AnswerCache(tmp_path, mode="fallback")
    _ask(replay, "s1")
    queried = len(replay.executor.queries)
    again = _ask(replay, "s2")
    assert again.cached_at is None and len(replay.executor.queries) > queried
