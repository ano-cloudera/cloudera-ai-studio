from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.db.platform_models import SemanticModelRow, SemanticTermRow
from app.semantic.context import glossary_phrase_map
from app.semantic_runtime.publish_governance import build_publish_governance


def _term(version_id: uuid.UUID, term: str, synonyms: list[str], dimensions: list[str]) -> SemanticTermRow:
    return SemanticTermRow(
        id=uuid.uuid4(),
        semantic_version_id=version_id,
        key=term.replace(" ", "_"),
        term=term,
        definition="x",
        synonyms=synonyms,
        related_metric_keys=[],
        related_dimension_keys=dimensions,
        related_entity_keys=[],
        metadata_={},
    )


def test_published_governance_carries_the_glossary_and_no_demo_profile() -> None:
    session = MagicMock()
    version_id = uuid.uuid4()
    model = SemanticModelRow(
        id=uuid.uuid4(), workspace_id=uuid.uuid4(), project_id=uuid.uuid4(), name="Fulfillment", key="fulfillment"
    )
    session.get.return_value = MagicMock(version_number=3)
    session.execute.return_value.scalars.return_value = iter(
        [_term(version_id, "kurir", ["courier"], ["delivery_shipments_carrier"])]
    )
    doc = build_publish_governance(session, version_id=version_id, model=model, datasets={"delivery_shipments": {}})
    assert doc["scope"]["semantic_model_key"] == "fulfillment"
    assert doc["glossary"][0]["term"] == "kurir"
    assert "runtime_extensions" not in doc
    assert glossary_phrase_map(doc) == [(("kurir", "courier"), "delivery_shipments_carrier")]


def test_a_model_published_with_the_old_phrase_map_still_maps_its_words() -> None:
    governance = {"runtime_extensions": {"breakdown": {"phrase_map": [{"phrases": ["segmen"], "dimension": "customers_segment"}]}}}
    assert glossary_phrase_map(governance) == [(("segmen",), "customers_segment")]
