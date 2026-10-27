#!/usr/bin/env python3
"""Smoke-check Gemini config (same env keys as backend-test)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.llm.registry import ProviderRegistry  # noqa: E402


async def _probe() -> None:
    settings = get_settings()
    print(f"default_llm_provider={settings.default_llm_provider}")
    print(f"gemini_model={settings.gemini_model}")
    print(f"gemini_key_set={bool(settings.gemini_api_key.get_secret_value())}")
    registry = ProviderRegistry(settings)
    gemini = next(m for m in registry.list_models() if m.provider == "gemini")
    print(f"gemini_available={gemini.available} reason={gemini.reason or '-'}")
    if not gemini.available:
        return
    provider = registry.resolve("gemini", settings.gemini_model)

    from pydantic import BaseModel

    class Ping(BaseModel):
        answer: str

    result = await provider.generate_structured(
        [{"role": "user", "content": 'Reply JSON only: {"answer":"pong"}'}],
        Ping,
        temperature=0,
        max_tokens=64,
    )
    print(f"probe_ok={result.answer!r}")


def main() -> int:
    try:
        asyncio.run(_probe())
    except Exception as exc:
        print(f"probe_failed={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
