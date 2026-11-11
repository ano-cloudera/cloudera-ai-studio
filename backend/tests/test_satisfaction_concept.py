"""A question about NPS or CSAT is answerable when the chosen metric is about satisfaction, and only then."""
from __future__ import annotations

from types import SimpleNamespace

from app.ask_data.intent_satisfaction import validate_registry_resolution

REGISTRY = SimpleNamespace(dataset_fields={})


def _definition(name: str, description: str, synonyms: list[str]) -> dict:
    return {"name": name, "description": description, "base_dataset": "d", "allowed_dimensions": [], "ai_context": {"synonyms": synonyms}}


def test_an_nps_metric_answers_a_question_about_nps() -> None:
    definition = _definition("net_promoter_score", "Promoters minus detractors as a percentage of all answers.", ["NPS", "net promoter"])
    result = validate_registry_resolution("Berapa NPS kita?", {"metric": "net_promoter_score", "dimensions": []}, definition=definition, registry=REGISTRY)
    assert result.intent_complete and not result.unresolved_constraints


def test_a_csat_metric_answers_a_question_about_customer_satisfaction() -> None:
    definition = _definition("average_csat", "Average satisfaction score from 1 to 5.", ["csat", "kepuasan pelanggan"])
    result = validate_registry_resolution("Berapa customer satisfaction kita?", {"metric": "average_csat", "dimensions": []}, definition=definition, registry=REGISTRY)
    assert result.intent_complete


def test_a_metric_about_something_else_still_cannot_answer_a_satisfaction_question() -> None:
    definition = _definition("total_revenue", "Net amount paid, after discounts.", ["revenue", "sales"])
    result = validate_registry_resolution("Berapa satisfaction kita?", {"metric": "total_revenue", "dimensions": []}, definition=definition, registry=REGISTRY)
    assert not result.intent_complete
    assert result.unresolved_constraints == ["customer_satisfaction"]
    assert result.reason_code == "INSUFFICIENT_CONTEXT"
