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
WORKSPACE_KEY = "ask_data.workspace"


def _resolved(key: str, file_name: str) -> str:
    try:
        from app.core.config import get_settings
        from app.prompt_management.resolver import PromptResolver

        text = PromptResolver(get_settings()).resolve(key).content.strip()
        if text:
            return text
    except Exception:  # noqa: BLE001 - a prompt that cannot be resolved must not stop an answer: the file applies
        logger.warning("managed_prompt_fallback key=%s", key)
    return (PROMPT_DIR / file_name).read_text(encoding="utf-8")


def managed_prompt(key: str, file_name: str) -> str:
    """The prompt, with the workspace's own instructions (Prompts: Workspace instructions) added after it when there are any."""
    text = _resolved(key, file_name)
    if key == WORKSPACE_KEY:
        return text
    extra = _resolved(WORKSPACE_KEY, "workspace_instructions.md").strip()
    if not extra:
        return text
    return f"{text.rstrip()}\n\n## Additional instructions from this workspace\nThese add to the rules above. Where they conflict with the rules about figures, filters or data, the rules above win.\n\n{extra}\n"


# The prompts that write a data answer, with their file defaults; their active text is part of what makes an answer.
ANSWER_PROMPTS: tuple[tuple[str, str], ...] = (
    ("ask_data.system", "global_system.md"),
    ("ask_data.analyst", "result_analyst.md"),
    ("ask_data.agent", "agent_tools.md"),
    ("ask_data.agent_report", "agent_tool_report.md"),
    ("ask_data.turn_reader", "conversation_rewrite.md"),
)


def prompts_fingerprint() -> str:
    """A short hash of the active text of the answer prompts: a cached answer written under other prompts is not served after a
    prompt is published (Prompts page or scripts/push_prompts.py). Empty when they cannot be read, so caching still works."""
    import hashlib

    try:
        digest = hashlib.sha256()
        for key, file_name in ANSWER_PROMPTS:
            digest.update(key.encode())
            digest.update(managed_prompt(key, file_name).encode("utf-8"))
        return digest.hexdigest()[:16]
    except Exception:  # noqa: BLE001
        logger.warning("prompts_fingerprint_unavailable")
        return ""
