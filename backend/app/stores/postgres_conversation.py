from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.models import AnalysisOutput, ChartSpec
from app.db.platform_engine import get_session_factory
from app.db.platform_models import ConversationRow, MessageRow, ProjectRow


class PostgresConversationStore:
    def __init__(self, database_url: str, *, default_project_id: uuid.UUID) -> None:
        self._session_factory = get_session_factory(database_url)
        self._default_project_id = default_project_id

    def _get_or_create_conversation(self, session: Session, external_session_id: str) -> ConversationRow:
        row = session.execute(
            select(ConversationRow).where(
                ConversationRow.project_id == self._default_project_id,
                ConversationRow.external_session_id == external_session_id,
            )
        ).scalar_one_or_none()
        if row:
            return row
        row = ConversationRow(
            project_id=self._default_project_id,
            external_session_id=external_session_id,
        )
        session.add(row)
        session.flush()
        return row

    def append(
        self,
        session_id: str,
        question: str,
        answer: AnalysisOutput,
        rows: list[dict],
        chart: ChartSpec | None,
        provider: str,
        model: str,
        *,
        status: str = "",
        strategy: str = "",
        session_frame: dict | None = None,
    ) -> None:
        payload = {
            "question": question,
            "answer": json.loads(answer.model_dump_json()),
            "rows": rows,
            "chart_spec": json.loads(chart.model_dump_json()) if chart else None,
            "provider": provider,
            "model": model,
            "status": status,
            "strategy": strategy,
            "session_frame": session_frame or {},
        }
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            conv = self._get_or_create_conversation(session, session_id)
            session.add(
                MessageRow(
                    conversation_id=conv.id,
                    role="assistant",
                    content_text=question,
                    response_json=payload,
                    status=status,
                    strategy=strategy,
                )
            )
            conv.last_message_at = now
            conv.updated_at = now
            session.commit()

    def load(self, session_id: str, limit: int = 20) -> list[dict]:
        with self._session_factory() as session:
            conv = session.execute(
                select(ConversationRow).where(
                    ConversationRow.project_id == self._default_project_id,
                    ConversationRow.external_session_id == session_id,
                )
            ).scalar_one_or_none()
            if not conv:
                return []
            messages = session.execute(
                select(MessageRow)
                .where(MessageRow.conversation_id == conv.id)
                .order_by(MessageRow.created_at.desc())
                .limit(limit)
            ).scalars().all()
        loaded: list[dict] = []
        for msg in reversed(messages):
            body = msg.response_json or {}
            loaded.append(
                {
                    "question": body.get("question") or msg.content_text,
                    "answer": body.get("answer") or {},
                    "rows": body.get("rows") or [],
                    "chart_spec": body.get("chart_spec"),
                    "provider": body.get("provider") or "",
                    "model": body.get("model") or "",
                    "status": body.get("status") or msg.status or "",
                    "strategy": body.get("strategy") or msg.strategy or "",
                    "session_frame": body.get("session_frame") or {},
                    "timestamp": msg.created_at.isoformat() if msg.created_at else "",
                }
            )
        return loaded

    def delete_session(self, session_id: str) -> int:
        session_id = (session_id or "").strip()
        if not session_id:
            return 0
        with self._session_factory() as db:
            conv = db.execute(
                select(ConversationRow).where(
                    ConversationRow.project_id == self._default_project_id,
                    ConversationRow.external_session_id == session_id,
                )
            ).scalar_one_or_none()
            if not conv:
                return 0
            count = len(conv.messages)
            db.execute(delete(MessageRow).where(MessageRow.conversation_id == conv.id))
            db.delete(conv)
            db.commit()
            return count
