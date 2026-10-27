"""Route Ask Data to OSSIE workflow vs tempo_agent_v3 (Phase B2)."""

from __future__ import annotations

import re
from typing import Any, Literal

from app.core.config import Settings

Route = Literal["ossie", "v3"]

_V3_HINT = re.compile(
    r"\b("
    r"dc|distribution center|gudang partner|cabang partner|"
    r"penumpukan|stok dc|store stock|dc stock|"
    r"top\s*\d+|tertinggi|terendah|pareto|peringkat|ranking|"
    r"analisa.*perbaik|rekomendasi operasional"
    r")\b",
    re.IGNORECASE,
)


def resolve_ask_data_route(
    question: str,
    settings: Settings,
    *,
    semantic_resolution: dict[str, Any] | None = None,
) -> Route:
    mode = (settings.ask_data_routing or "auto").strip().lower()
    resolution = semantic_resolution or {}
    if mode == "ossie":
        return "ossie"
    if mode == "auto":
        # Prefer OSSIE when the catalog already resolves a metric (Phase C),
        # even if LOCAL_AGENT_PRIMARY=1 in .env (sidecar optional).
        if resolution.get("status") == "resolved":
            return "ossie"
        if resolution.get("status") in ("needs_clarification", "fallback"):
            return "ossie"
        if _V3_HINT.search(question or ""):
            return "v3"
        if settings.local_agent_primary:
            return "v3"
        return "v3"
    if mode == "v3" or settings.local_agent_primary:
        return "v3"
    return "ossie"


def v3_agent_available(settings: Settings) -> bool:
    return bool((settings.local_agent_base_url or "").strip())
