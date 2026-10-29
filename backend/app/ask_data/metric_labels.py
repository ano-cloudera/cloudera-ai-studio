"""Human-readable metric labels for clarifications and UI."""

from __future__ import annotations

import re
from typing import Any


def humanize_metric_label(*, name: str | None = None, definition: dict[str, Any] | None = None) -> str:
    from app.semantic.banking_demo_catalog import display_name_for_metric

    if name:
        catalog = display_name_for_metric(name)
        if catalog:
            return catalog
    raw = ""
    if definition:
        ai = definition.get("ai_context") if isinstance(definition.get("ai_context"), dict) else {}
        raw = str(definition.get("display_name") or (ai.get("display_name") if ai else None) or "").strip()
        if not raw and name and re.fullmatch(r"[a-z0-9_]+", str(name).strip(), flags=re.IGNORECASE):
            # A slug beats the description, which can be a long business definition rather than a title.
            raw = str(name).strip()
        if not raw:
            raw = str(definition.get("description") or "").strip()
    if not raw and name:
        raw = str(name).strip()
    if raw.lower().startswith("suggested metric "):
        raw = raw[17:].strip()
    if raw and not re.fullmatch(r"[a-z0-9_]+", raw, flags=re.IGNORECASE):
        return raw
    token = raw or name or "Metric"
    return token.replace("_", " ").strip().title()
