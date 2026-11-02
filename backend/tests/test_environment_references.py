from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.v1.environment import environment_references
from app.main import create_app


def test_only_secret_like_and_forwarded_names_are_listed_without_values() -> None:
    env = {
        "GEMINI_API_KEY": "secret-1",
        "TRINO_PASSWORD": "secret-2",
        "MY_TOOL_TOKEN": "secret-3",
        "MY_DB_USER": "someone",
        "AMP_FORWARD_ENV": "MY_DB_USER, MISSING_ONE",
        "PATH": "/usr/bin",
        "TRINO_HOST": "host",
        "OPENAI_API_KEY": "",
        "STUDIO_API_TOKEN": "internal",
        "QDRANT_API_KEY": "internal",
        "CDSW_APIV2_KEY": "internal",
    }
    references = environment_references(env)
    names = [r["name"] for r in references]
    assert names == ["GEMINI_API_KEY", "MY_DB_USER", "MY_TOOL_TOKEN", "TRINO_PASSWORD"]
    assert {r["ref"] for r in references} == {f"env://{n}" for n in names}
    assert {r["name"]: r["kind"] for r in references}["GEMINI_API_KEY"] == "api_key"
    assert {r["name"]: r["kind"] for r in references}["TRINO_PASSWORD"] == "password"
    assert all("secret" not in str(r) and "someone" not in str(r) for r in references)  # never a value


def test_the_endpoint_is_served() -> None:
    response = TestClient(create_app()).get("/api/v1/environment/references")
    assert response.status_code == 200 and isinstance(response.json()["references"], list)
