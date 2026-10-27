import pytest

from app.services.conversational import ConversationalIntent, classify_conversational_intent


class FakeProvider:
    def __init__(self, intent: ConversationalIntent) -> None:
        self.intent = intent

    async def generate_structured(self, messages, response_model, **kwargs):
        return self.intent


@pytest.mark.asyncio
async def test_sell_in_vs_sell_out_concept_classified_conversational() -> None:
    q = "Halo, apa bedanya sell-in Tempo dan sell-out Alfamart untuk tim manajemen?"
    provider = FakeProvider(
        ConversationalIntent(
            is_conversational=True,
            attach_domain_catalog=False,
            pipeline_question=q,
            rationale="concept explain",
        )
    )
    result = await classify_conversational_intent(provider=provider, question=q, first_turn=True)
    assert result.is_conversational is True


@pytest.mark.asyncio
async def test_analytic_sell_in_question_classified_not_conversational() -> None:
    q = "Berapa total sell-in Tempo Q4 2024?"
    provider = FakeProvider(
        ConversationalIntent(
            is_conversational=False,
            attach_domain_catalog=False,
            pipeline_question=q,
            rationale="numeric analytic",
        )
    )
    result = await classify_conversational_intent(provider=provider, question=q, first_turn=True)
    assert result.is_conversational is False
