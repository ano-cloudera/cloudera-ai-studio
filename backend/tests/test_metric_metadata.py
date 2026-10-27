"""Tests for metric allowed-dimension metadata at publish time."""

from types import SimpleNamespace

from app.semantic_registry.metric_metadata import resolve_allowed_dimension_keys_for_publish


def test_resolve_uses_stored_subset_when_valid():
    dimensions = [
        SimpleNamespace(key="city", source_entity_key="customers"),
        SimpleNamespace(key="segment", source_entity_key="customers"),
        SimpleNamespace(key="channel", source_entity_key="transactions"),
    ]
    relationships = [
        SimpleNamespace(from_entity_key="transactions", to_entity_key="customers"),
    ]
    keys = resolve_allowed_dimension_keys_for_publish(
        metric_source_entity_key="transactions",
        metric_metadata={"allowed_dimension_keys": ["city", "bogus", "channel"]},
        entity_dimension_keys=["channel", "city", "segment"],
        dimensions=dimensions,
        relationships=relationships,
    )
    assert keys == ["channel", "city"]


def test_resolve_falls_back_to_entity_dims_when_stored_empty():
    dimensions = [SimpleNamespace(key="city", source_entity_key="customers")]
    keys = resolve_allowed_dimension_keys_for_publish(
        metric_source_entity_key="customers",
        metric_metadata={"allowed_dimension_keys": []},
        entity_dimension_keys=["city"],
        dimensions=dimensions,
        relationships=[],
    )
    assert keys == ["city"]


def test_resolve_defaults_when_metadata_missing():
    keys = resolve_allowed_dimension_keys_for_publish(
        metric_source_entity_key="customers",
        metric_metadata={},
        entity_dimension_keys=["city", "segment"],
        dimensions=[],
        relationships=[],
    )
    assert keys == ["city", "segment"]
