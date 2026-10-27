import pytest

from app.services.conversational import (
    ConversationalIntent,
    UnderstandingMode,
    _session_block,
    _understanding_mode,
    classify_conversational_intent,
    understand_turn,
)


class FakeProvider:
    def __init__(self, intent: ConversationalIntent) -> None:
        self.intent = intent
        self.messages: list | None = None

    async def generate_structured(self, messages, response_model, **kwargs):
        self.messages = messages
        return self.intent


@pytest.mark.asyncio
async def test_classify_uses_llm_structured_output() -> None:
    provider = FakeProvider(
        ConversationalIntent(
            is_conversational=True,
            attach_domain_catalog=True,
            pipeline_question="Halo",
            rationale="greeting",
        )
    )
    result = await classify_conversational_intent(
        provider=provider,
        question="Halo",
        first_turn=True,
    )
    assert result.is_conversational is True
    assert result.attach_domain_catalog is True
    assert provider.messages is not None
    assert "Halo" in provider.messages[1]["content"]


def test_understanding_mode_skip_when_session_has_context_but_no_bindings() -> None:
    history = [
        {
            "question": "Top 10 DC Alfamart",
            "answer": {"direct_answer": "Berikut ranking DC."},
        }
    ]
    session = _session_block(history)
    assert session["result_catalog"] == []
    assert _understanding_mode(session, "Berapa total sell-in Tempo Q4 2024?") == UnderstandingMode.SKIP


def test_understanding_mode_lite_on_first_turn() -> None:
    session = _session_block([])
    assert _understanding_mode(session, "Halo") == UnderstandingMode.LITE


@pytest.mark.asyncio
async def test_understand_turn_skip_does_not_call_provider() -> None:
    class FailProvider:
        async def generate_structured(self, *args, **kwargs):
            raise AssertionError("LLM should not be called in skip mode")

    history = [{"question": "prior", "answer": {"direct_answer": "ok"}}]
    result = await understand_turn(
        provider=FailProvider(),
        question="Tampilkan top 10 material sell-in Q4 2024",
        conversation_history=history,
    )
    assert result.is_conversational is False
    assert result.rationale.startswith("skip_")


@pytest.mark.asyncio
async def test_classify_defaults_to_analytic_on_provider_error() -> None:
    class FailProvider:
        async def generate_structured(self, *args, **kwargs):
            from app.llm.base import ProviderError

            raise ProviderError("fail")

    result = await classify_conversational_intent(
        provider=FailProvider(),
        question="Halo",
        first_turn=True,
    )
    assert result.is_conversational is False
