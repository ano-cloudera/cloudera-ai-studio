"""A warehouse query runs after the platform database session is closed: a query of several seconds must not hold one of the few
pooled connections (with a wide semantic model the value lookups and Home's queries used them all up and answers lost their filters)."""
from __future__ import annotations

import asyncio
import uuid

from app.ask_data import datasource_executor
from app.ask_data.datasource_executor import RoutedQueryExecutor
from tests.conftest import isolated_settings


class FakeSession:
    open_sessions = 0

    def __enter__(self):
        FakeSession.open_sessions += 1
        return self

    def __exit__(self, *exc):
        FakeSession.open_sessions -= 1
        return False


def test_the_warehouse_query_runs_with_no_platform_session_open(monkeypatch) -> None:
    seen: dict[str, int] = {}

    class Prepared:
        def run(self, sql, *, max_rows):
            seen["sessions_while_querying"] = FakeSession.open_sessions
            return {"columns": ["v"], "rows": [{"v": 1}], "row_count": 1}

    class Executor:
        def __init__(self, session, *, settings):
            pass

        def prepare(self, *, context, workspace_id, project_id):
            seen["sessions_while_preparing"] = FakeSession.open_sessions
            return Prepared()

    monkeypatch.setattr(datasource_executor, "ConnectorDatasourceExecutor", Executor)
    executor = RoutedQueryExecutor(isolated_settings(), FakeSession)
    state = {
        "workspace_id": str(uuid.uuid4()), "project_id": str(uuid.uuid4()),
        "datasource_context": {"connector_id": str(uuid.uuid4()), "connector_type": "trino", "connector_name": "t", "legacy_fallback": False},
    }
    result = asyncio.run(executor.execute("SELECT 1 AS v", state))
    assert result["rows"] == [{"v": 1}]
    assert seen == {"sessions_while_preparing": 1, "sessions_while_querying": 0}
