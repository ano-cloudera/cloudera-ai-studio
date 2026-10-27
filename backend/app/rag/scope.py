from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.platform_models import LibraryRow


def rag_scope_from_history(history: list[dict]) -> list[str]:
    for entry in reversed(history):
        frame = entry.get("session_frame")
        if not isinstance(frame, dict):
            continue
        if frame.get("mode") != "rag":
            continue
        raw = frame.get("rag_library_ids")
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item).strip()]
    return []


def resolve_library_ids(
    session: Session,
    *,
    project_id: uuid.UUID,
    requested: list[str] | None,
    history: list[dict],
    default_library_ids: list[str],
) -> list[uuid.UUID]:
    raw_ids = requested if requested else rag_scope_from_history(history)
    if not raw_ids and default_library_ids:
        raw_ids = default_library_ids
    if not raw_ids:
        return []

    parsed: list[uuid.UUID] = []
    for item in raw_ids:
        try:
            parsed.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    if not parsed:
        return []

    rows = session.execute(
        select(LibraryRow).where(
            LibraryRow.id.in_(parsed),
            LibraryRow.project_id == project_id,
        )
    ).scalars().all()
    allowed = {row.id for row in rows}
    return [lib_id for lib_id in parsed if lib_id in allowed]


def bounded_rag_dialog(history: list[dict], *, max_turns: int) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for entry in history[-max_turns * 2 :]:
        q = entry.get("question")
        ans = entry.get("answer")
        if not isinstance(q, str) or not q.strip():
            continue
        if isinstance(ans, dict):
            text = (ans.get("direct_answer") or ans.get("executive_summary") or "").strip()
        else:
            text = ""
        if text:
            turns.append({"role": "user", "content": q.strip()})
            turns.append({"role": "assistant", "content": text[:800]})
    return turns[-max_turns * 2 :]


def build_rag_session_frame(*, library_ids: list[uuid.UUID], project_id: uuid.UUID) -> dict[str, Any]:
    return {
        "mode": "rag",
        "rag_library_ids": [str(i) for i in library_ids],
        "rag_project_id": str(project_id),
    }
