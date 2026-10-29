from __future__ import annotations

from types import SimpleNamespace

import yaml

from app.semantic_registry import governance_pipeline
from app.semantic_registry.governance_pipeline import SemanticGovernancePipeline
from app.semantic_registry.types import RuntimeArtifact


def _large_artifact() -> RuntimeArtifact:
    metrics = [
        {
            "name": f"metric_{i}",
            "description": "A governed metric with a deliberately long business definition " * 4,
            "expression": {"dialects": [{"dialect": "ANSI_SQL", "expression": f"SUM(column_{i})"}]},
        }
        for i in range(60)
    ]
    content = yaml.safe_dump({"version": "0.2.0.dev0", "name": "big", "metrics": metrics}, sort_keys=False)
    assert len(content) > 8000
    return RuntimeArtifact(
        adapter="ossie",
        version="1",
        uri=None,
        checksum="abc",
        content_preview=content[:8000],
        content=content,
        metadata={"entities": 0, "metrics": 60, "dimensions": 0, "relationships": 0},
    )


def test_artifact_validation_parses_the_full_document_not_the_truncated_preview(monkeypatch) -> None:
    artifact = _large_artifact()
    monkeypatch.setattr(
        governance_pipeline.OssieRuntimeAdapter, "generate_artifact", lambda self, *a, **k: artifact
    )
    issues: list = []
    pipeline = SemanticGovernancePipeline.__new__(SemanticGovernancePipeline)
    pipeline._session = SimpleNamespace()
    pipeline._validate_artifact("v1", [], [object()] * 60, [], [], issues.append)

    assert not [i for i in issues if getattr(i, "code", "") == "artifact_generation_failed"], issues
