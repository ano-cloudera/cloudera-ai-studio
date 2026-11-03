"""The chat stream must keep context variables alive across generator steps (model registry resolution)."""
from __future__ import annotations

import contextvars
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api

_marker: contextvars.ContextVar[str | None] = contextvars.ContextVar("stream_ctx_marker", default=None)


class _Service:
    def normalize_request(self, body):
        return body

    async def stream(self, body):
        _marker.set("registry-model")  # set in the first step, like prepare_request
        yield {"type": "status", "value": "first"}
        yield {"type": "status", "value": _marker.get() or "lost"}  # read in a later step


def test_stream_keeps_context_between_steps(monkeypatch):
    monkeypatch.setattr(chat_api, "_validate_selection", lambda *_: None)
    app = FastAPI()
    app.include_router(chat_api.router)
    app.state.chat_service = _Service()
    body = {"session_id": "s1", "question": "q", "provider": "gemini", "model": "m", "mode": "mcp"}
    with TestClient(app) as client:
        text = client.post("/chat/stream", json=body).text
    assert "registry-model" in text
    assert "lost" not in text
