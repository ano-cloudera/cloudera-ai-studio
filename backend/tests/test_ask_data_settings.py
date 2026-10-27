"""Ask Data starter settings (workspace settings_json)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_metadata_sqlite_portability import sqlite_platform  # noqa: F401 — fixture


def test_starters_empty_by_default(sqlite_platform) -> None:
    settings, _url = sqlite_platform
    client = TestClient(create_app(settings))
    response = client.get("/api/v1/ask-data/starters")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"configured", "semantic_runtime"}
    if payload["source"] == "configured":
        assert payload["questions"] == []
    else:
        assert len(payload["questions"]) >= 1
    assert payload["caption"] == "Start with a question"


def test_put_settings_and_resolve_starters(sqlite_platform) -> None:
    settings, _url = sqlite_platform
    client = TestClient(create_app(settings))
    put = client.put(
        "/api/v1/ask-data/settings",
        json={
            "starter_questions_caption": "Mulai dengan pertanyaan",
            "starter_questions": [
                "Berapa total saldo nasabah aktif?",
                "Siapa nasabah dengan transaksi terbesar bulan ini?",
            ],
            "starter_source": "configured",
            "question_bank_limit": 3,
            "question_bank_domain": None,
            "question_bank_difficulty": None,
        },
    )
    assert put.status_code == 200
    starters = client.get("/api/v1/ask-data/starters")
    assert starters.status_code == 200
    body = starters.json()
    assert body["caption"] == "Mulai dengan pertanyaan"
    assert len(body["questions"]) == 2
    assert body["questions"][0]["question"].startswith("Berapa total saldo")


def test_question_bank_mode(sqlite_platform) -> None:
    settings, _url = sqlite_platform
    client = TestClient(create_app(settings))
    put = client.put(
        "/api/v1/ask-data/settings",
        json={
            "starter_questions_caption": "Demo",
            "starter_questions": [],
            "starter_source": "question_bank",
            "question_bank_limit": 2,
            "question_bank_domain": "sat_oos",
            "question_bank_difficulty": None,
        },
    )
    assert put.status_code == 200
    starters = client.get("/api/v1/ask-data/starters")
    assert starters.status_code == 200
    body = starters.json()
    assert body["source"] == "question_bank"
    assert len(body["questions"]) == 2
    assert all(item["domain"] == "sat_oos" for item in body["questions"])
