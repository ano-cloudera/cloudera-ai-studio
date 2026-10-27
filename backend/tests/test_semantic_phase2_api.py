"""Phase 2 semantic API extensions."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.semantic_overview_service import SemanticOverviewService


def test_overview_counts_structure():
    session = MagicMock()
    model_id = uuid.uuid4()
    ws, proj = uuid.uuid4(), uuid.uuid4()
    model = MagicMock()
    model.id = model_id
    model.workspace_id = ws
    model.project_id = proj
    model.name = "Commercial"
    model.key = "commercial"
    model.active_version_id = None
    model.updated_at = None
    session.get.return_value = model
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.execute.return_value.scalar_one.return_value = 0
    svc = SemanticOverviewService(session)
    out = svc.model_overview(model_id=model_id, workspace_id=ws, project_id=proj)
    assert out["counts"]["entities"] == 0
    assert "state" in out


def test_list_query_sort_whitelist():
    from app.semantic_registry.list_query import apply_list_query

    rows = [MagicMock(name="b", key="b", updated_at="2"), MagicMock(name="a", key="a", updated_at="1")]
    for r in rows:
        r.name = r._mock_name
        r.description = ""
        r.schema = None
        r.table_name = None
        r.view_name = None
    filtered, total = apply_list_query(
        rows,
        search=None,
        sort="invalid_field",
        order="asc",
        page=1,
        page_size=10,
        allowed_sort=frozenset({"name", "key"}),
        search_text=lambda r: r.name,
    )
    assert total == 2
    assert filtered[0].name == "a"
