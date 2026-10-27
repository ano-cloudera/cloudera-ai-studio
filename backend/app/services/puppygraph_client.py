"""Optional PuppyGraph client (Phase C7). Disabled unless PUPPYGRAPH_ENABLED=true."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings


logger = logging.getLogger(__name__)

_STUB_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "puppygraph_schema_stub.yaml"


@lru_cache(maxsize=1)
def load_puppygraph_schema_stub() -> dict[str, Any]:
    if not _STUB_PATH.is_file():
        return {}
    data = yaml.safe_load(_STUB_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


class PuppyGraphClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.base_url = (settings.puppygraph_base_url or "").strip().rstrip("/")
        self.enabled = bool(settings.puppygraph_enabled and self.base_url)

    @property
    def configured(self) -> bool:
        return self.enabled

    def schema_summary(self) -> dict[str, Any]:
        stub = load_puppygraph_schema_stub()
        return {
            "enabled": self.enabled,
            "base_url": self.base_url or None,
            "vertex_labels": [v.get("label") for v in stub.get("vertices") or [] if isinstance(v, dict)],
            "edge_labels": [e.get("label") for e in stub.get("edges") or [] if isinstance(e, dict)],
            "max_hops": (stub.get("limits") or {}).get("max_hops"),
        }

    async def ping(self) -> bool:
        if not self.enabled:
            return False
        try:
            import httpx
        except ImportError:
            logger.warning("puppygraph_ping_skipped httpx not installed")
            return False
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
                response = await client.get("/health")
                return response.status_code < 500
        except Exception:
            logger.info("puppygraph_unreachable base_url=%s", self.base_url)
            return False
