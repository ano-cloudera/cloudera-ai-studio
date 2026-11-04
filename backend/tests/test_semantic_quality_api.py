"""Instructions, example questions and benchmark guards through the real API (SQLite)."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_metadata_sqlite_portability import sqlite_platform  # noqa: F401 - fixture


def _model(client: TestClient) -> str:
    return client.post("/api/v1/semantic/models", json={"name": "Quality", "key": f"q.{uuid.uuid4().hex[:6]}"}).json()["model"]["id"]


def test_instructions_and_examples_are_saved_per_model_and_survive_a_reload(sqlite_platform) -> None:
    settings, _url = sqlite_platform
    client = TestClient(create_app(settings))
    first, second = _model(client), _model(client)
    assert client.get(f"/api/v1/semantic/models/{first}/knowledge").json()["examples"] == []

    saved = client.put(
        f"/api/v1/semantic/models/{first}/knowledge",
        json={
            "instructions": "  Late means after the service level.  ",
            "examples": [{"question": "Late rate for Jawa Timur", "expected_value": 16.34, "tolerance": 0.05, "match": "Jawa Timur"}],
        },
    )
    assert saved.status_code == 200 and saved.json()["instructions"] == "Late means after the service level."

    again = client.get(f"/api/v1/semantic/models/{first}/knowledge").json()
    assert again["examples"][0]["question"] == "Late rate for Jawa Timur" and again["examples"][0]["expected_value"] == 16.34
    assert client.get(f"/api/v1/semantic/models/{second}/knowledge").json()["instructions"] == ""  # another model is untouched


def test_an_unknown_model_is_a_404(sqlite_platform) -> None:
    settings, _url = sqlite_platform
    client = TestClient(create_app(settings))
    assert client.get(f"/api/v1/semantic/models/{uuid.uuid4()}/knowledge").status_code == 404


def test_a_benchmark_needs_an_expected_value_and_a_published_model(sqlite_platform) -> None:
    settings, _url = sqlite_platform
    client = TestClient(create_app(settings))
    model = _model(client)
    body = {"provider": "gemini", "model": "m"}

    nothing = client.post(f"/api/v1/semantic/models/{model}/benchmarks/run", json=body)
    assert nothing.status_code == 422 and nothing.json()["detail"]["code"] == "NO_BENCHMARKS"

    client.put(f"/api/v1/semantic/models/{model}/knowledge", json={"instructions": "", "examples": [{"question": "q", "expected_value": 1.0}]})
    unpublished = client.post(f"/api/v1/semantic/models/{model}/benchmarks/run", json=body)
    assert unpublished.status_code == 409 and unpublished.json()["detail"]["code"] == "NOT_PUBLISHED"
