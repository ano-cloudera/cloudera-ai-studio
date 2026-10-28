#!/usr/bin/env python3
"""M1 PostgreSQL smoke validation (local Docker / dev only)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import SecretStr
from sqlalchemy import select, text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.models import AnalysisOutput, AskDataRequest, ChartSpec  # noqa: E402
from app.db.platform_engine import get_session_factory  # noqa: E402
from app.db.platform_models import ProjectRow, WorkspaceRow  # noqa: E402
from app.main import create_app  # noqa: E402
from app.stores.factory import (  # noqa: E402
    build_conversation_store,
    build_usage_store,
    init_postgres_platform,
)
from app.stores.postgres_conversation import PostgresConversationStore  # noqa: E402
from app.stores.postgres_usage import PostgresUsageStore  # noqa: E402
from app.stores.sqlite_conversation import SQLiteConversationStore  # noqa: E402
from app.stores.sqlite_usage import SQLiteUsageStore  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _database_url() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SMOKE_DATABASE_URL")
        or "postgresql+psycopg://m1:m1pass@127.0.0.1:55432/accelerator"
    ).strip()


def _postgres_settings(tmp_sqlite: Path) -> Settings:
    return Settings(
        _env_file=None,
        state_store="postgres",
        database_url=_database_url(),
        conversation_db_path=tmp_sqlite / "conv.sqlite",
        usage_db_path=tmp_sqlite / "usage.sqlite",
        data_backend="duckdb",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
        gemini_api_key=SecretStr(""),
        openai_api_key=SecretStr(""),
    )


def _check_tables(url: str) -> None:
    factory = get_session_factory(url)
    with factory() as session:
        tables = session.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
        ).scalars().all()
    expected = {"alembic_version", "conversations", "messages", "projects", "usage_events", "workspaces"}
    missing = expected - set(tables)
    if missing:
        raise RuntimeError(f"missing tables after migration: {sorted(missing)}")


def _check_seed(url: str) -> None:
    factory = get_session_factory(url)
    with factory() as session:
        ws = session.execute(select(WorkspaceRow).where(WorkspaceRow.slug == "default")).scalar_one()
        proj = session.execute(
            select(ProjectRow).where(
                ProjectRow.workspace_id == ws.id,
                ProjectRow.slug == "reference_impala",
            )
        ).scalar_one()
    if not proj.ossie_root_path:
        raise RuntimeError("default project missing ossie_root_path")


def _store_roundtrip(settings: Settings, session_id: str) -> None:
    conv = build_conversation_store(settings)
    usage = build_usage_store(settings)
    if not isinstance(conv, PostgresConversationStore):
        raise RuntimeError(f"expected PostgresConversationStore, got {type(conv).__name__}")
    if not isinstance(usage, PostgresUsageStore):
        raise RuntimeError(f"expected PostgresUsageStore, got {type(usage).__name__}")

    answer = AnalysisOutput(
        direct_answer="smoke",
        executive_summary="smoke",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="smoke",
        chart_spec=None,
    )
    conv.append(
        session_id,
        "smoke question?",
        answer,
        [{"value": 1}],
        ChartSpec(type="kpi", title="Smoke", x="", y="value"),
        "gemini",
        "gemini-smoke",
        status="SUCCESS",
        strategy="governed",
    )
    history = conv.load(session_id, limit=5)
    if not history:
        raise RuntimeError("conversation history empty after append")

    rid = str(uuid.uuid4())
    usage.record(
        request_id=rid,
        session_id=session_id,
        provider="gemini",
        model="gemini-smoke",
        strategy="governed",
        status="SUCCESS",
        prompt_tokens=10,
        completion_tokens=5,
        llm_calls=1,
    )
    totals = usage.totals(days=7)
    if totals.get("total_tokens", 0) < 15:
        raise RuntimeError(f"usage totals unexpected: {totals}")


class _FakeChatService:
    async def run(self, request: AskDataRequest):
        from app.core.models import AskDataResponse, QueryData, Timings

        return AskDataResponse(
            request_id=str(uuid.uuid4()),
            session_id=request.session_id,
            status="SUCCESS",
            provider=request.provider,
            model=request.model,
            strategy="governed",
            answer=AnalysisOutput(
                direct_answer="10",
                executive_summary="Total 10",
                insights=[],
                business_implications=[],
                caveats=[],
                data_reference="result",
                chart_spec=None,
            ),
            data=QueryData(columns=["value"], rows=[{"value": 10}], row_count=1, execution_ms=1),
            chart_spec=None,
            timings=Timings(total_ms=2),
        )

    async def stream(self, request: AskDataRequest):
        yield {"type": "progress", "stage": "querying_data", "label": "Querying data"}
        yield {"type": "done", "response": await self.run(request)}


def _http_smoke(settings: Settings, session_id: str) -> None:
    app = create_app(settings)
    app.state.chat_service = _FakeChatService()
    client = TestClient(app)

    ready = client.get("/health/ready").json()
    if ready.get("components", {}).get("state_store") != "postgres":
        raise RuntimeError(f"readiness state_store unexpected: {ready}")

    ws = client.get("/api/v1/workspaces/default")
    if ws.status_code != 200:
        raise RuntimeError(f"/api/v1/workspaces/default -> {ws.status_code}")

    stream = client.post(
        "/chat/stream",
        json={
            "session_id": session_id,
            "question": "smoke governed question",
            "provider": "qwen",
            "model": "qwen-model",
        },
    )
    if stream.status_code != 200:
        raise RuntimeError(f"/chat/stream -> {stream.status_code}")
    frames = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
    if not frames or frames[-1].get("type") != "done":
        raise RuntimeError("SSE missing terminal done frame")

    summary = client.get("/usage/summary?days=7")
    if summary.status_code != 200:
        raise RuntimeError(f"/usage/summary -> {summary.status_code}")


def _fallback_smoke(tmp: Path) -> None:
    bad = Settings(
        _env_file=None,
        state_store="postgres",
        database_url="postgresql+psycopg://invalid:invalid@127.0.0.1:59999/nodb",
        conversation_db_path=tmp / "fb_conv.sqlite",
        usage_db_path=tmp / "fb_usage.sqlite",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    conv = build_conversation_store(bad)
    usage = build_usage_store(bad)
    if not isinstance(conv, SQLiteConversationStore):
        raise RuntimeError("fallback conversation store should be SQLite")
    if not isinstance(usage, SQLiteUsageStore):
        raise RuntimeError("fallback usage store should be SQLite")

    sqlite_only = Settings(
        _env_file=None,
        state_store="sqlite",
        conversation_db_path=tmp / "only_conv.sqlite",
        usage_db_path=tmp / "only_usage.sqlite",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    if not isinstance(build_conversation_store(sqlite_only), SQLiteConversationStore):
        raise RuntimeError("sqlite mode should use SQLite conversation store")


def main() -> int:
    tmp = ROOT / "runtime" / "m1_smoke_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    url = _database_url()
    print(f"DATABASE_URL host check: {url.split('@')[-1] if '@' in url else url}")

    _check_tables(url)
    print("OK alembic tables present")

    settings = _postgres_settings(tmp)
    init_postgres_platform(settings)
    _check_seed(url)
    print("OK default workspace/project bootstrap")

    session_id = f"m1-smoke-{uuid.uuid4()}"
    _store_roundtrip(settings, session_id)
    print("OK conversation + usage persistence")

    _http_smoke(settings, session_id)
    print("OK STATE_STORE=postgres startup + SSE + platform API")

    # Simulate restart: new store instances, same DB session id
    settings_restart = _postgres_settings(tmp)
    reloaded = build_conversation_store(settings_restart).load(session_id, limit=5)
    if not reloaded:
        raise RuntimeError("history missing after simulated restart")
    print("OK persistence survives restart (new store instances)")

    _fallback_smoke(tmp)
    print("OK sqlite mode + postgres-unavailable fallback")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
