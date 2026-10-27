"""SEM-P1 Phase 1 gates for structured Ask Data context."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ask_data.datasource_router import AskDataDatasourceRouter
from app.ask_data.structured_context_resolver import resolve_structured_ask
from app.ask_data.table_context_id import decode_raw_table_id, encode_raw_table_id
from app.ask_data.validation import validate_ask_data_sql
from app.chat.context_sources import ContextSourceError, apply_context_sources
from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()
from app.core.models import AskDataRequest, ChatContextSource
from app.semantic.context import SemanticContextService, TablePolicy


def test_sem_p1_001_table_id_roundtrip():
    cid = uuid.uuid4()
    raw = encode_raw_table_id(connector_id=cid, catalog=None, schema="public", table="sales")
    ref = decode_raw_table_id(raw)
    assert ref is not None
    assert ref.connector_id == cid
    assert ref.schema == "public"
    assert ref.table == "sales"


def test_sem_p1_002_raw_table_select_only(settings: Settings):
    ctx = SemanticContextService.__new__(SemanticContextService)
    state = {
        "datasource_context": {
            "legacy_fallback": False,
            "connector_type": "postgres",
            "dialect": "postgres",
            "allowed_physical_tables": ["public.sales"],
        },
        "raw_table_policy": {
            "qualified_name": "public.sales",
            "columns": ["amount", "sale_date"],
        },
    }
    ok = validate_ask_data_sql(
        "SELECT d.amount, d.sale_date FROM public.sales d LIMIT 10",
        ctx,
        state=state,
        max_rows=200,
    )
    assert ok.valid


def test_sem_p1_003_raw_table_blocks_write(settings: Settings):
    ctx = SemanticContextService.__new__(SemanticContextService)
    state = {
        "datasource_context": {
            "legacy_fallback": False,
            "dialect": "postgres",
            "allowed_physical_tables": ["public.sales"],
        },
        "raw_table_policy": {"qualified_name": "public.sales", "columns": ["amount"]},
    }
    bad = validate_ask_data_sql("DELETE FROM public.sales", ctx, state=state)
    assert not bad.valid


def test_sem_p1_004_raw_table_scoped_table(settings: Settings):
    ctx = SemanticContextService.__new__(SemanticContextService)
    state = {
        "datasource_context": {
            "legacy_fallback": False,
            "dialect": "postgres",
            "allowed_physical_tables": ["public.sales"],
        },
        "raw_table_policy": {"qualified_name": "public.sales", "columns": ["amount"]},
    }
    bad = validate_ask_data_sql("SELECT d.amount FROM public.other d", ctx, state=state)
    assert not bad.valid


def test_sem_p1_005_cross_project_connector_rejected(settings: Settings):
    session = MagicMock()
    ws_a, proj_a = uuid.uuid4(), uuid.uuid4()
    connector_id = uuid.uuid4()
    registry = MagicMock()
    registry.get_connector.side_effect = Exception("not found")
    with patch("app.ask_data.datasource_router.ConnectorRegistryService", return_value=registry):
        router = AskDataDatasourceRouter(session, settings=settings)
        result = router.resolve_raw_table(
            workspace_id=ws_a,
            project_id=proj_a,
            connector_id=connector_id,
            catalog=None,
            schema="public",
            table="sales",
        )
    assert result.code == "CONNECTOR_NOT_FOUND"


def test_sem_p1_009_broken_metric_no_silent_fallback():
    session = MagicMock()
    metric_id = uuid.uuid4()
    model_id = uuid.uuid4()
    version_id = uuid.uuid4()
    metric = SimpleNamespace(
        id=metric_id,
        key="missing_metric",
        name="Missing Metric",
        synonyms=[],
        semantic_version_id=version_id,
    )
    version = SimpleNamespace(id=version_id, semantic_model_id=model_id)
    model = SimpleNamespace(
        id=model_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        key="commercial",
        active_version_id=version_id,
    )
    session.get.side_effect = lambda cls, pk: {metric_id: metric, version_id: version, model_id: model}.get(pk)
    bundle = SimpleNamespace(
        context=SimpleNamespace(
            _registry_runtime=True,
            registry=SimpleNamespace(
                metrics={"other": {}},
                resolve_metric=lambda _q: {"status": "unsupported"},
            ),
            metric_definition=lambda _k: (_ for _ in ()).throw(KeyError("missing")),
        ),
        mode="runtime",
    )
    req = AskDataRequest(
        session_id="s",
        question="show total",
        provider="gemini",
        model="gemini-3.8-flash",
        context_sources=[ChatContextSource(type="semantic_metric", id=str(metric_id), name="Total Sales")],
    )
    with patch("app.ask_data.structured_context_resolver.SemanticRuntimeLoader.get") as loader:
        loader.return_value.load_from_session.return_value = bundle
        out = resolve_structured_ask(
            session,
            settings=Settings(),
            workspace_id=model.workspace_id,
            project_id=model.project_id,
            request=req,
            semantic_context=bundle.context,
            question=req.question,
        )
    assert out.explicit_error is not None
    assert out.resolution is None


def test_sem_p1_011_ambiguous_auto_clarification():
    session = MagicMock()
    ws, proj = uuid.uuid4(), uuid.uuid4()
    c1 = uuid.uuid4()
    conn = SimpleNamespace(id=c1, name="Impala", enabled=True, connector_type="impala")
    registry = MagicMock()
    registry.list_connectors.return_value = [conn]
    tables_payload = {
        "tables": [
            {"name": "sales_sell_in", "schema": "gold", "catalog": None},
            {"name": "sales_sell_out", "schema": "gold", "catalog": None},
        ]
    }
    discovery = MagicMock()
    discovery.list_tables.return_value = tables_payload
    req = AskDataRequest(
        session_id="s",
        question="compare sales_sell_in and sales_sell_out by month",
        provider="gemini",
        model="gemini-3.8-flash",
    )
    with patch("app.ask_data.structured_context_resolver.ConnectorRegistryService", return_value=registry), patch(
        "app.ask_data.structured_context_resolver.MetadataDiscoveryService", return_value=discovery
    ), patch.object(AskDataDatasourceRouter, "resolve_raw_table") as resolve_raw:
        resolve_raw.return_value = SimpleNamespace(
            legacy_fallback=False,
            qualified_sources={"raw": "gold.sales_sell_in"},
            allowed_physical_tables=frozenset({"gold.sales_sell_in"}),
            to_dict=lambda: {"legacy_fallback": False},
        )
        out = resolve_structured_ask(
            session,
            settings=Settings(),
            workspace_id=ws,
            project_id=proj,
            request=req,
            semantic_context=MagicMock(),
            question=req.question,
        )
    assert out.clarification is not None
    assert out.clarification.reason == "AMBIGUOUS_DATA_SOURCE"
    assert len(out.clarification.options) >= 2


def test_sem_p1_012_clarification_options_structured():
    from app.services.chat import ChatService
    from app.core.models import AskDataClarification

    svc = ChatService.__new__(ChatService)
    req = AskDataRequest(session_id="s", question="q", provider="gemini", model="m")
    payload = SimpleNamespace(
        reason="AMBIGUOUS_DATA_SOURCE",
        message="pick one",
        options=[{"type": "table", "id": "tr:x", "name": "Sales Sell In"}],
    )
    resp = ChatService._clarification_response(svc, req, request_id="r1", payload=payload, started=0.0)
    assert resp.status == "clarification_required"
    assert resp.clarification is not None
    assert resp.clarification.options[0].type == "table"


def test_sem_p1_017_mixed_family_rejected():
    req = AskDataRequest(
        session_id="s1",
        question="q",
        provider="gemini",
        model="gemini-3.8-flash",
        context_sources=[
            ChatContextSource(type="knowledge_library", id=str(uuid.uuid4()), name="Docs"),
            ChatContextSource(type="table", id="tr:bad", name="sales"),
        ],
    )
    with pytest.raises(ContextSourceError) as exc:
        apply_context_sources(
            req,
            session=object(),
            project_id=uuid.uuid4(),
            conversation_history=[],
            settings=object(),
        )
    assert exc.value.code == "mixed_context_unsupported"


def test_sem_p1_020_dialect_preserved_in_raw_router(settings: Settings):
    session = MagicMock()
    connector_id = uuid.uuid4()
    row = SimpleNamespace(
        id=connector_id,
        enabled=True,
        connector_type="trino",
        name="Trino",
    )
    registry = MagicMock()
    registry.get_connector.return_value = row
    with patch("app.ask_data.datasource_router.ConnectorRegistryService", return_value=registry):
        router = AskDataDatasourceRouter(session, settings=settings)
        ctx = router.resolve_raw_table(
            workspace_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            connector_id=connector_id,
            catalog="hive",
            schema="gold",
            table="sales",
        )
    assert ctx.dialect == "trino"
    assert "hive" in next(iter(ctx.qualified_sources.values())).casefold()
