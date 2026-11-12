"""One rule picks the model Ask Data answers from, for every path: the pinned one, else the only one, else the one published last."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.ask_data import structured_context_resolver as scr

WS, PROJ = uuid.uuid4(), uuid.uuid4()


class Session:
    def __init__(self, rows: dict) -> None:
        self.rows = rows

    def get(self, _model, key):
        return self.rows.get(key)


def _model(name: str, version_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), key=name, workspace_id=WS, project_id=PROJ, active_version_id=version_id)


def _setup(monkeypatch, pinned: str | None, *models_and_times):
    rows: dict = {WS: SimpleNamespace(settings_json={})}
    models = []
    for model, published in models_and_times:
        rows[model.id] = model
        rows[model.active_version_id] = SimpleNamespace(published_at=published, updated_at=published)
        models.append(model)
    monkeypatch.setattr(scr, "read_ask_data_settings", lambda _json: SimpleNamespace(default_semantic_model_id=pinned or "", auto_attach_semantic_model=True))
    monkeypatch.setattr(scr, "_published_models_for_project", lambda session, **_: models)
    return Session(rows)


def test_the_pinned_model_wins(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    c360, fuel = _model("customer_360", uuid.uuid4()), _model("fuel_distribution", uuid.uuid4())
    session = _setup(monkeypatch, str(c360.id), (c360, now - timedelta(days=1)), (fuel, now))
    assert scr.default_semantic_model(session, workspace_id=WS, project_id=PROJ) is c360


def test_without_a_pin_the_model_published_last_wins_not_an_arbitrary_one(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    c360, fuel = _model("customer_360", uuid.uuid4()), _model("fuel_distribution", uuid.uuid4())
    session = _setup(monkeypatch, None, (c360, now - timedelta(days=1)), (fuel, now))
    assert scr.default_semantic_model(session, workspace_id=WS, project_id=PROJ) is fuel
    session = _setup(monkeypatch, None, (fuel, now), (c360, now - timedelta(days=1)))
    assert scr.default_semantic_model(session, workspace_id=WS, project_id=PROJ) is fuel


def test_one_or_no_published_model(monkeypatch) -> None:
    only = _model("fuel_distribution", uuid.uuid4())
    assert scr.default_semantic_model(_setup(monkeypatch, None, (only, None)), workspace_id=WS, project_id=PROJ) is only
    assert scr.default_semantic_model(_setup(monkeypatch, None), workspace_id=WS, project_id=PROJ) is None


def test_every_entry_point_answers_from_the_default_model(monkeypatch) -> None:
    """The judge calls /chat (run) and the UI /chat/stream (stream): both, and the agent's reading, load the default model
    first. Only run did, so the judge's greeting was right while the UI's greeting described another published model."""
    import asyncio

    from app.core.models import AskDataRequest
    from app.services.chat import ChatService
    from tests.replay_support import Replay

    replay = Replay(monkeypatch)
    called: list[str] = []
    monkeypatch.setattr(ChatService, "use_default_semantic_model", lambda self, request: called.append(request.question))

    def ask(question: str) -> AskDataRequest:
        return AskDataRequest(session_id="s", question=question, provider="qwen", model="m")

    async def stream_all() -> None:
        async for _ in replay.service.stream(ask("via stream")):
            pass

    asyncio.run(stream_all())
    asyncio.run(replay.service.run(ask("via run")))
    asyncio.run(replay.service.read_conversation(ask("via the agent")))
    assert called == ["via stream", "via run", "via the agent"]
