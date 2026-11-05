from app.ask_data.conversation import last_turn, previous_turns, turn_memory
from app.core.models import AnalysisOutput
from app.services.history import ConversationStore


def test_history_persists_provider_model_and_structured_answer(tmp_path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite")
    answer = AnalysisOutput(
        direct_answer="10",
        executive_summary="Total is 10",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="query result",
        chart_spec=None,
    )

    store.append(
        "session-1",
        "question",
        answer,
        [{"value": 10}],
        None,
        "gemini",
        "gemini-model",
        status="SUCCESS",
        strategy="governed",
    )

    history = store.load("session-1")
    assert history[0]["provider"] == "gemini"
    assert history[0]["model"] == "gemini-model"
    assert history[0]["status"] == "SUCCESS"
    assert history[0]["strategy"] == "governed"
    assert history[0]["answer"]["direct_answer"] == "10"
    assert "reasoning" not in str(history).lower()


def test_delete_session_removes_all_turns(tmp_path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite")
    answer = AnalysisOutput(
        direct_answer="ok",
        executive_summary="ok",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="x",
        chart_spec=None,
    )
    store.append("sess-a", "q1", answer, [], None, "gemini", "m", status="SUCCESS", strategy="governed")
    store.append("sess-a", "q2", answer, [], None, "gemini", "m", status="SUCCESS", strategy="governed")
    store.append("sess-b", "q3", answer, [], None, "gemini", "m", status="SUCCESS", strategy="governed")
    assert store.delete_session("sess-a") == 2
    assert store.load("sess-a") == []
    assert len(store.load("sess-b")) == 1


def test_history_persists_the_turn_memory(tmp_path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite")
    frame = turn_memory(
        question="and per carrier?",
        standalone_question="Late rate per carrier in Jawa Timur in March 2026",
        status="SUCCESS",
        strategy="governed",
        metric="late_delivery_rate",
        dimensions=["delivery_shipments_carrier"],
        scope="Jawa Timur, March 2026",
    )
    answer = AnalysisOutput(
        direct_answer="NusaCargo is the latest.",
        executive_summary="ok",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="x",
        chart_spec=None,
    )
    store.append(
        "s1", "and per carrier?", answer, [{"carrier": "NusaCargo", "metric_value": 13.2}], None, "gemini", "gemini-model",
        status="SUCCESS", strategy="governed", session_frame=frame,
    )
    history = store.load("s1")
    assert last_turn(history) == {"last_metric": "late_delivery_rate", "last_dimensions": ["delivery_shipments_carrier"]}
    shown = previous_turns(history, labels={"late_delivery_rate": "Late delivery rate"})[0]
    assert shown["read_as"] == "Late rate per carrier in Jawa Timur in March 2026"
    assert shown["metric"] == "Late delivery rate"
    assert shown["filters_and_period"] == "Jawa Timur, March 2026"
    assert shown["first_rows"] == [{"carrier": "NusaCargo", "metric_value": 13.2}]


def test_a_failed_turn_leaves_no_metric_to_continue() -> None:
    frame = turn_memory(
        question="x", standalone_question=None, status="ERROR", strategy="unsupported", metric="m", dimensions=[], scope=None
    )
    assert "metric" not in frame
    assert last_turn([{"session_frame": frame}]) is None
