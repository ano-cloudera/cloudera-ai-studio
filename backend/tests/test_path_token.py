from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security.path_token import PathTokenMiddleware

TOKEN = "s3cret-token"


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/v1/items")
    def items():
        return {"items": [1]}

    app.add_middleware(PathTokenMiddleware, token=TOKEN)
    return TestClient(app)


def test_calls_without_the_token_are_not_found_except_the_liveness_check() -> None:
    client = _client()
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/items").status_code == 404
    assert client.get("/wrong/api/v1/items").status_code == 404
    assert client.get("/docs").status_code == 404


def test_the_token_prefix_reaches_the_route() -> None:
    client = _client()
    response = client.get(f"/{TOKEN}/api/v1/items")
    assert response.status_code == 200 and response.json() == {"items": [1]}


def test_the_docs_page_works_under_the_token() -> None:
    client = _client()
    assert client.get(f"/{TOKEN}/openapi.json").status_code == 200
    assert f"/{TOKEN}/openapi.json" in client.get(f"/{TOKEN}/docs").text
