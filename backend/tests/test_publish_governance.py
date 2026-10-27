from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.db.platform_models import SemanticModelRow, SemanticTermRow
from app.semantic_runtime.publish_governance import (
    build_publish_governance,
    build_runtime_extensions_block,
)


def test_build_runtime_extensions_includes_profile_and_phrase_map() -> None:
    datasets = {"transactions": {"source": "banking_demo.transactions"}}
    term = SemanticTermRow(
        id=uuid.uuid4(),
        semantic_version_id=uuid.uuid4(),
        key="tipe_akun",
        term="tipe akun",
        definition="Customer account type",
        synonyms=["jenis akun"],
        related_metric_keys=[],
        related_dimension_keys=["customers_segment"],
        related_entity_keys=[],
        metadata_={},
    )
    block = build_runtime_extensions_block(datasets, [term])
    assert block is not None
    assert block.get("profile") == "banking_demo"
    phrase_map = (block.get("breakdown") or {}).get("phrase_map") or []
    assert any(item.get("dimension") == "customers_segment" for item in phrase_map)


def test_build_publish_governance_writes_glossary_and_extensions() -> None:
    session = MagicMock()
    version_id = uuid.uuid4()
    model = SemanticModelRow(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="Banking Analytics",
        key="banking_analytics",
    )
    term = SemanticTermRow(
        id=uuid.uuid4(),
        semantic_version_id=version_id,
        key="failed_rate",
        term="failed transaction rate",
        definition="Share of failed tx",
        synonyms=[],
        related_metric_keys=["transactions_failed_transaction_rate"],
        related_dimension_keys=[],
        related_entity_keys=[],
        metadata_={},
    )
    session.get.return_value = MagicMock(version_number=3)
    session.execute.return_value.scalars.return_value = iter([term])

    doc = build_publish_governance(
        session,
        version_id=version_id,
        model=model,
        datasets={"transactions": {"source": "banking_demo.transactions"}},
    )
    assert doc["scope"]["semantic_model_key"] == "banking_analytics"
    assert len(doc["glossary"]) == 1
    assert doc["glossary"][0]["term"] == "failed transaction rate"
    assert "runtime_extensions" in doc
