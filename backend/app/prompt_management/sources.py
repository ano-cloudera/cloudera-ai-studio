from __future__ import annotations

from pathlib import Path

from app.core.config import BACKEND_ROOT, Settings
from app.prompt_management.keys import ASK_DATA_SYSTEM, RAG_INSUFFICIENT_EVIDENCE, RAG_SYSTEM
from app.rag.prompt import INSUFFICIENT_ANSWER_EN

PROMPT_DIR = BACKEND_ROOT / "prompts"


class FilePromptSource:
    """Legacy disk prompts — default when DB has no active override."""

    FILE_MAP: dict[str, str] = {
        ASK_DATA_SYSTEM: "global_system.md",
        RAG_SYSTEM: "rag_system.txt",
    }

    TEXT_MAP: dict[str, str] = {
        RAG_INSUFFICIENT_EVIDENCE: INSUFFICIENT_ANSWER_EN,
    }

    def get(self, prompt_key: str) -> str | None:
        if prompt_key in self.TEXT_MAP:
            return self.TEXT_MAP[prompt_key]
        filename = self.FILE_MAP.get(prompt_key)
        if not filename:
            return None
        path = PROMPT_DIR / filename
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return None


class DatabasePromptSource:
    def __init__(self, session) -> None:
        self._session = session

    def get_active_content(
        self,
        *,
        prompt_key: str,
        workspace_id,
        project_id,
    ) -> tuple[str | None, str | None]:
        """Return (content, scope_label) for highest-precedence active prompt."""
        from app.services.prompt_service import PromptService

        svc = PromptService(self._session)
        effective = svc.resolve_effective(prompt_key=prompt_key, workspace_id=workspace_id, project_id=project_id)
        if not (effective.content or "").strip() or effective.source == "file":
            return None, None
        return effective.content, effective.source
