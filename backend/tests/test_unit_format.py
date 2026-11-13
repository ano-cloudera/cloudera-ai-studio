"""A metric's unit decides how its figures are shown, so the UI never guesses it from a column name."""
from app.semantic_registry.runtime_adapter import _unit_format


def test_units_map_to_a_display_format() -> None:
    assert _unit_format("percent") == "percent" and _unit_format("%") == "percent"
    assert _unit_format("IDR") == "currency_idr" and _unit_format("minutes") == "minutes"
    assert _unit_format("KL") == "quantity" and _unit_format("stations") == "quantity"  # a count or volume, unit in the name
    assert _unit_format("") is None and _unit_format(None) is None
