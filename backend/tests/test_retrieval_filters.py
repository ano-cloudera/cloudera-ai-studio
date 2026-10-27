from __future__ import annotations

import pytest

from app.vectors.filters import VectorSearchFilters, build_qdrant_filter


def test_requires_workspace_and_project():
    with pytest.raises(ValueError):
        VectorSearchFilters(workspace_id="", project_id="p").validate_scoped()


def test_build_filter_includes_library_any():
    filt = build_qdrant_filter(
        VectorSearchFilters(workspace_id="w", project_id="p", library_ids=("l1", "l2"))
    )
    assert filt is not None
    assert len(filt.must) >= 3
