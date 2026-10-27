"""Certified golden questions embedded in published OSSIE bundles."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.platform_models import SemanticModelRow, WorkspaceRow
from app.workspace.ask_data_settings import read_ask_data_settings

_DEFAULT_BANKING_QUESTIONS = [
    "What is the total transaction amount?",
    "Show total transaction amount by channel.",
    "Berapa total customer kita saat ini?",
    "Berapa failed transaction rate?",
    "Top 5 customer segment berdasarkan jumlah transaksi.",
]


def build_certified_golden_questions(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    model: SemanticModelRow | None,
) -> list[dict[str, Any]]:
    workspace = session.get(WorkspaceRow, workspace_id)
    settings = read_ask_data_settings(workspace.settings_json if workspace else None)
    questions: list[str] = []
    if settings.starter_source == "configured" and settings.starter_questions:
        questions.extend(settings.starter_questions)
    if not questions and model and str(model.key or "").casefold() in {"banking_analytics", "retail_banking_analytics"}:
        questions = list(_DEFAULT_BANKING_QUESTIONS)
    deduped: list[str] = []
    seen: set[str] = set()
    for q in questions:
        text = " ".join(str(q).split()).strip()
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        deduped.append(text[:500])
    return [{"question": q, "certified": True} for q in deduped[:15]]
