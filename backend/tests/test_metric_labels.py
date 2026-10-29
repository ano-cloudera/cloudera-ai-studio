from __future__ import annotations

from app.ask_data.metric_labels import humanize_metric_label


def test_label_uses_metric_name_not_a_long_business_definition():
    label = humanize_metric_label(
        name="approval_rate",
        definition={"description": "Share of credit applications that were approved, as a percentage (0-100)."},
    )
    assert label == "Approval Rate"


def test_label_prefers_explicit_display_name():
    assert humanize_metric_label(name="approval_rate", definition={"display_name": "Approval %"}) == "Approval %"
