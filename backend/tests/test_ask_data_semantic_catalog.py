"""Unit tests for Ask Data semantic catalog payload builder."""

from __future__ import annotations

import uuid

from app.ask_data.semantic_catalog_api import build_semantic_catalog_payload
from app.workspace.ask_data_settings import write_ask_data_settings, AskDataSettings


def test_catalog_empty_without_published_model() -> None:
    class _Session:
        def get(self, _cls, _id):
            return None

        def execute(self, _stmt):
            class _Scalars:
                def __iter__(self):
                    return iter([])

            class _R:
                def scalars(self):
                    return _Scalars()

            return _R()

    ws = uuid.uuid4()
    proj = uuid.uuid4()
    payload = build_semantic_catalog_payload(
        _Session(),  # type: ignore[arg-type]
        workspace_id=ws,
        project_id=proj,
        settings_json=write_ask_data_settings(None, AskDataSettings()),
    )
    assert payload["model"] is None
    assert payload["metrics"] == []
