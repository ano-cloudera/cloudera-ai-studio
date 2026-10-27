"""Phase 2A list/pagination/delete/recent-definitions API."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.semantic_registry.list_query import apply_list_query


def test_dimensions_list_pagination_whitelist():
    rows = [MagicMock(name="b", key="b"), MagicMock(name="a", key="a")]
    for r in rows:
        r.name = r._mock_name
        r.description = ""
        r.source_column = "c"
        r.source_entity_key = "e"
        r.synonyms = []
    filtered, total = apply_list_query(
        rows,
        search=None,
        sort="invalid",
        order="desc",
        page=1,
        page_size=1,
        allowed_sort=frozenset({"name", "modified"}),
        search_text=lambda r: r.name,
    )
    assert total == 2
    assert len(filtered) == 1
    assert filtered[0].name == "b"


def test_recent_definitions_type_filter_logic():
    from app.api.v1 import semantic as sem

    rows = [
        sem._RecentDefinitionRow(object_id="1", object_kind="metric", key="m", name="M", type="Metric", definition="", source="s", status="Ready", updated_at=None, created_at=None),
        sem._RecentDefinitionRow(object_id="2", object_kind="glossary", key="g", name="G", type="Glossary", definition="", source="—", status="Ready", updated_at=None, created_at=None),
    ]
    filtered = [r for r in rows if r.type.casefold() == "metric"]
    assert len(filtered) == 1
