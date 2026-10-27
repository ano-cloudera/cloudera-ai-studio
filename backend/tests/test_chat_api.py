from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.core.models import AnalysisOutput, AskDataRequest, AskDataResponse, QueryData, Timings
from app.db.base import DataBackendError
from app.main import create_app
from app.api import chat as chat_api
from app.llm.base import ProviderError
from app.ask_data.legacy_executor import ImpalaQueryExecutor
from app.services.chat import ChatService
from app.services.conversational import TurnUnderstanding

from conftest import isolated_settings
from test_workflow import FakeContext


class FakeChatService:
    def normalize_request(self, request: AskDataRequest) -> AskDataRequest:
        return request

    async def run(self, request):
        return AskDataResponse(
            request_id="request-1",
            session_id=request.session_id,
            status="SUCCESS",
            provider=request.provider,
            model=request.model,
            strategy="governed",
            answer=AnalysisOutput(direct_answer="10", executive_summary="Total 10", insights=[], business_implications=[], caveats=[], data_reference="result", chart_spec=None),
            data=QueryData(columns=["value"], rows=[{"value": 10}], row_count=1, execution_ms=1),
            chart_spec=None,
            timings=Timings(total_ms=2),
        )

    async def stream(self, request):
        for stage in ("understanding_request", "retrieving_context", "preparing_query", "validating_query", "querying_data", "analyzing_result"):
            yield {"type": "progress", "stage": stage, "label": stage.replace("_", " ").title()}
        yield {"type": "done", "response": await self.run(request)}


def client() -> TestClient:
    app = create_app(isolated_settings())
    app.state.chat_service = FakeChatService()
    return TestClient(app)


def test_chat_rejects_model_not_exposed_by_backend() -> None:
    response = client().post("/chat", json={"session_id": "s", "question": "q", "provider": "qwen", "model": "arbitrary"})
    assert response.status_code == 422
    assert "not configured" in response.text


def test_chat_stream_emits_progress_and_terminal_response() -> None:
    response = client().post(
        "/chat/stream",
        json={"session_id": "s", "question": "q", "provider": "qwen", "model": "/models/Qwen3.8-27B-AWQ"},
    )
    assert response.status_code == 200
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [frame["stage"] for frame in frames if frame["type"] == "progress"] == [
        "understanding_request", "retrieving_context", "preparing_query", "validating_query", "querying_data", "analyzing_result"
    ]
    assert frames[-1]["type"] == "done"
    assert frames[-1]["response"]["status"] == "SUCCESS"
    assert response.headers["x-accel-buffering"] == "no"


def test_chat_stream_heartbeat_does_not_cancel_slow_terminal_response(monkeypatch) -> None:
    class SlowChatService(FakeChatService):
        async def stream(self, request):
            await asyncio.sleep(0.03)
            yield {"type": "done", "response": await self.run(request)}

    test_client = client()
    test_client.app.state.chat_service = SlowChatService()
    monkeypatch.setattr(chat_api, "HEARTBEAT_SECONDS", 0.005)

    response = test_client.post(
        "/chat/stream",
        json={"session_id": "s", "question": "q", "provider": "qwen", "model": "/models/Qwen3.8-27B-AWQ"},
    )

    assert ": keep-alive" in response.text
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_impala_executor_does_not_block_the_event_loop() -> None:
    executor = ImpalaQueryExecutor(Settings(_env_file=None))

    class SlowBackend:
        def execute(self, *_):
            time.sleep(0.03)
            return SimpleNamespace(
                columns=[SimpleNamespace(name="value")],
                records=lambda: [{"value": 1}],
                row_count=1,
                telemetry=SimpleNamespace(query_latency_ms=30),
            )

    executor.backend = SlowBackend()
    task = asyncio.create_task(executor.execute("SELECT 1", "request-1"))
    await asyncio.sleep(0.005)

    assert not task.done()
    assert (await task)["rows"] == [{"value": 1}]


@pytest.mark.asyncio
async def test_chat_reports_impala_auth_failure_without_exposing_driver_details() -> None:
    class FailedWorkflow:
        async def ainvoke(self, _initial):
            raise DataBackendError("IMPALA_AUTH_FAILED")

    class EmptyHistory:
        def load(self, *_args, **_kwargs):
            return []

    class ExplainingProvider:
        async def generate_structured(self, *_args, **_kwargs):
            return AnalysisOutput(
                direct_answer="Impala authentication failed for this deployment.",
                executive_summary="Impala authentication failed.",
                insights=[],
                business_implications=[],
                caveats=["Impala authentication is required for this query."],
                data_reference="error",
                chart_spec=None,
            )

    class FakeRegistry:
        def resolve(self, *_args, **_kwargs):
            return ExplainingProvider()

    service = object.__new__(ChatService)
    service.workflow = FailedWorkflow()
    service.history = EmptyHistory()
    service.settings = isolated_settings()
    service.dependencies = SimpleNamespace(
        provider_registry=FakeRegistry(),
        semantic_context=FakeContext({"status": "resolved", "metric": "company_fill_rate", "definition": {"base_dataset": "monthly_executive"}}),
        query_executor=SimpleNamespace(),
        sql_validator=SimpleNamespace(),
        settings=isolated_settings(),
        session_factory=None,
        local_agent_client=None,
        judge_max_iterations=2,
        judge_enabled=False,
        usage_tracker=None,
    )
    service.usage_tracker = None

    async def _turn(_request, _history, **_kwargs):
        return TurnUnderstanding(
            is_conversational=False,
            attach_domain_catalog=False,
            pipeline_question=_request.question,
        )

    service._understand_turn = _turn  # type: ignore[method-assign]
    service._sync_runtime_for_request = lambda: None  # type: ignore[method-assign]
    service._persist_turn = lambda *_a, **_k: None  # type: ignore[method-assign]
    service._attach_usage = lambda _req, resp: resp  # type: ignore[method-assign]
    service._runtime_bundle = None
    service._project_scope = None
    service._active_resolution = None

    request = AskDataRequest(
        session_id="session-1",
        question="Berapa fill rate?",
        provider="qwen",
        model="/models/Qwen3.8-27B-AWQ",
    )

    response = await service.run(request, force_ossie=True)

    assert response.status == "ERROR"
    assert "impala" in response.answer.direct_answer.casefold() or "autentikasi" in response.answer.direct_answer.casefold()
    assert response.request_id
    assert response.answer.caveats
    assert "Internal error details" not in " ".join(response.answer.caveats)
