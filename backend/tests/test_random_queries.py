from collections import Counter

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.semantic.questions import CURATED_CONTRACTS, QuestionBank
from app.semantic.context import SemanticContextService
from app.sql.validator import validate_sql


def test_question_bank_has_six_actual_domains_with_five_each() -> None:
    questions = QuestionBank().all()
    counts = Counter(question.domain for question in questions)

    assert len(questions) >= 30
    assert counts == {
        "sales": 5,
        "b2b": 5,
        "stock_tempo": 5,
        "stock_sat_idm": 5,
        "sat_oos": 5,
        "cross_domain": 5,
    }


def test_random_queries_endpoint_filters_and_bounds_limit() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))

    response = client.get("/random-queries?domain=b2b&difficulty=medium&limit=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body["questions"]) == 2
    assert all(item["domain"] == "b2b" and item["difficulty"] == "medium" for item in body["questions"])


def test_random_queries_endpoint_rejects_unknown_domain() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))

    response = client.get("/random-queries?domain=advertising")

    assert response.status_code == 422


def test_every_deterministically_resolved_curated_question_compiles_to_safe_sql() -> None:
    context = SemanticContextService()
    for item in QuestionBank().all():
        contract = CURATED_CONTRACTS[item.id]
        resolution = context.resolve(item.question)
        if contract.get("strategy") == "sql_fallback":
            assert resolution["status"] == "fallback"
            continue
        assert resolution["metric"] == contract["metric"]
        assert resolution["dimensions"] == contract["dimensions"]
        sql = context.compile_governed(resolution["metric"], item.question, resolution["dimensions"])
        result = validate_sql(sql, context)
        assert result.valid, f"{item.id}: {result.error}\n{sql}"
        for dimension in contract["dimensions"]:
            assert f"d.{dimension} AS {dimension}" in sql, f"{item.id}: missing {dimension}\n{sql}"

    assert len(CURATED_CONTRACTS) == 30
