from __future__ import annotations

from pathlib import Path

from app.core.config import BACKEND_ROOT, Settings
from app.core.language import detect_language
from app.retrieval.types import RetrievalCandidate

DEFAULT_PROMPT_PATH = BACKEND_ROOT / "prompts" / "rag_system.txt"

INSUFFICIENT_ANSWER_EN = (
    "The selected documents do not contain enough evidence to answer this question. "
    "Try the library that holds the relevant document, upload it, or rephrase the question."
)
INSUFFICIENT_ANSWER_ID = (
    "Data yang tersedia belum cukup untuk menjawab pertanyaan ini secara ter-grounding. "
    "Unggah dokumen yang relevan, pilih perpustakaan yang tepat, atau perjelas pertanyaan Anda."
)


def load_rag_system_prompt(
    settings: Settings,
    *,
    session=None,
    workspace_id=None,
    project_id=None,
) -> str:
    from app.prompt_management.keys import RAG_SYSTEM
    from app.prompt_management.resolver import PromptResolver

    resolver = PromptResolver(settings, session=session)
    text = resolver.resolve(RAG_SYSTEM, workspace_id=workspace_id, project_id=project_id).content
    if text.strip():
        return text.strip()
    path = Path(settings.rag_system_prompt_path or DEFAULT_PROMPT_PATH)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return "Answer from supplied evidence only. Do not invent sources."


def load_rag_insufficient_message(
    settings: Settings, *, session=None, workspace_id=None, project_id=None, question: str = ""
) -> str:
    from app.prompt_management.keys import RAG_INSUFFICIENT_EVIDENCE
    from app.prompt_management.resolver import PromptResolver

    resolver = PromptResolver(settings, session=session)
    text = resolver.resolve(RAG_INSUFFICIENT_EVIDENCE, workspace_id=workspace_id, project_id=project_id).content.strip()
    # A message edited in Prompt Management wins; the built-in default follows the question's language.
    if text and text not in (INSUFFICIENT_ANSWER_EN, INSUFFICIENT_ANSWER_ID):
        return text
    return INSUFFICIENT_ANSWER_ID if detect_language(question) == "id" else INSUFFICIENT_ANSWER_EN


def format_evidence_block(candidate: RetrievalCandidate, index: int) -> str:
    header = f"[{index}] chunk_id={candidate.chunk_id}"
    if candidate.filename:
        header += f" file={candidate.filename}"
    if candidate.page_number is not None:
        header += f" page={candidate.page_number}"
    if candidate.section:
        header += f" section={candidate.section}"
    return f"{header}\n{candidate.text.strip()}"


def build_rag_user_message(
    *,
    question: str,
    evidence: list[RetrievalCandidate],
    dialog: list[dict[str, str]],
) -> str:
    parts: list[str] = []
    if dialog:
        parts.append("Recent conversation (for follow-up context only):")
        for turn in dialog:
            role = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if content:
                parts.append(f"{role.upper()}: {content}")
        parts.append("")

    parts.append(f"Question: {question.strip()}")
    parts.append("")
    if evidence:
        parts.append("Evidence:")
        for idx, cand in enumerate(evidence, start=1):
            parts.append(format_evidence_block(cand, idx))
    else:
        parts.append("Evidence: (none retrieved)")
    return "\n".join(parts)
