from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.ask_data.datasource_router import AskDataDatasourceRouter
from app.ask_data.types import DatasourceRoutingError
from app.core.config import Settings


def _entity(*, key: str, connection_id: uuid.UUID | None, schema: str = "gold", table: str = "sales"):
    row = MagicMock()
    row.key = key
    row.name = key
    row.connection_id = connection_id
    row.catalog = None
    row.schema = schema
    row.table_name = table
    row.view_name = None
    return row


@pytest.fixture
def settings() -> Settings:
    return Settings()


def test_legacy_when_no_semantic_version(settings: Settings) -> None:
    session = MagicMock()
    router = AskDataDatasourceRouter(session, settings=settings)
    ctx = router.resolve_for_governed_metric(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        semantic_version_id=None,
        dataset_name="sales_monthly",
        bundle_mode="legacy",
    )
    assert ctx.legacy_fallback is True
    assert ctx.connector_id is None


def test_cross_connector_blocked(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    vid = uuid.uuid4()
    e1 = _entity(key="a", connection_id=c1)
    e2 = _entity(key="b", connection_id=c2)

    def fake_find(_session, *, semantic_version_id, dataset_name):
        return {"a": e1, "b": e2}.get(dataset_name)

    monkeypatch.setattr("app.ask_data.datasource_router.find_entity_for_dataset", fake_find)
    monkeypatch.setattr("app.ask_data.datasource_router.assert_version_in_project", lambda *a, **k: MagicMock())

    router = AskDataDatasourceRouter(session, settings=settings)
    result = router.resolve_entities(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        semantic_version_id=vid,
        dataset_names=["a", "b"],
        bundle_mode="runtime",
    )
    assert isinstance(result, DatasourceRoutingError)
    assert result.code == "CROSS_CONNECTOR_QUERY_UNSUPPORTED"


def test_mixed_legacy_and_connector_blocked(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    vid = uuid.uuid4()
    e1 = _entity(key="a", connection_id=uuid.uuid4())
    e2 = _entity(key="b", connection_id=None)

    def fake_find(_session, *, semantic_version_id, dataset_name):
        return {"a": e1, "b": e2}.get(dataset_name)

    monkeypatch.setattr("app.ask_data.datasource_router.find_entity_for_dataset", fake_find)
    monkeypatch.setattr("app.ask_data.datasource_router.assert_version_in_project", lambda *a, **k: MagicMock())

    router = AskDataDatasourceRouter(session, settings=settings)
    result = router.resolve_entities(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        semantic_version_id=vid,
        dataset_names=["a", "b"],
        bundle_mode="runtime",
    )
    assert isinstance(result, DatasourceRoutingError)
    assert result.code == "MIXED_LEGACY_CONNECTOR"
