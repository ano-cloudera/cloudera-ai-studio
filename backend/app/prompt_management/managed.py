"""The text of a managed prompt: the version published in Prompts when there is one, else the file in backend/prompts.

Used where a prompt decides the quality of an answer, so it can be tuned from the Prompts page or by scripts/push_prompts.py
without a redeploy. The resolution context (workspace, project) and the database session are those of the request being served;
outside a request, or without the platform database, the file is what applies.
"""
from __future__ import annotations

import logging

from app.core.config import BACKEND_ROOT

logger = logging.getLogger(__name__)

PROMPT_DIR = BACKEND_ROOT / "prompts"


def managed_prompt(key: str, file_name: str) -> str:
    try:
        from app.core.config import get_settings
        from app.prompt_management.resolver import PromptResolver

        text = PromptResolver(get_settings()).resolve(key).content.strip()
        if text:
            return text
    except Exception:  # noqa: BLE001 - a prompt that cannot be resolved must not stop an answer: the file applies
        logger.warning("managed_prompt_fallback key=%s", key)
    return (PROMPT_DIR / file_name).read_text(encoding="utf-8")
