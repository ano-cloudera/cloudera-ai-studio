from __future__ import annotations

import sys
from pathlib import Path

from pydantic import SecretStr

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
