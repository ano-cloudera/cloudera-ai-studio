from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Apply before any `app.main` import (module-level `app = create_app()`).
for _key in (
    "STATE_STORE",
    "DATABASE_URL",
    "OSSIE_PROJECT_ID",
    "DEFAULT_PROJECT_SLUG",
    "PROJECT_ID",
):
    os.environ.pop(_key, None)
os.environ["OSSIE_PROJECT_ID"] = "tempo_scan_impala"
os.environ["DEFAULT_PROJECT_SLUG"] = "tempo_scan_impala"
os.environ["STATE_STORE"] = "sqlite"
os.environ["DATABASE_URL"] = ""

from pydantic import SecretStr

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_ENV_KEYS = (
    "STATE_STORE",
    "DATABASE_URL",
    "OSSIE_PROJECT_ID",
    "DEFAULT_PROJECT_SLUG",
    "PROJECT_ID",
)


@pytest.fixture(autouse=True)
def _isolate_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent developer shell / CI env from overriding unit-test Settings kwargs."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def isolated_settings(**overrides) -> Settings:
    """Settings for unit tests — bypasses `.env` / process env (model_construct)."""
    base: dict = {
        "qwen_base_url": "https://qwen.internal/v1",
        "qwen_api_key": SecretStr("configured-token"),
        "qwen_model": "/models/Qwen3.8-27B-AWQ",
        "gemini_model": "gemini-configured",
        "gemini_api_key": SecretStr(""),
        "openai_model": "gpt-configured",
        "openai_api_key": SecretStr(""),
        "local_agent_base_url": "",
        "impala_host": "localhost",
        "impala_user": "svc",
        "impala_password": "secret",
    }
    base.update(overrides)
    return Settings.model_construct(**base)
