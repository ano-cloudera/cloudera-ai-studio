from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.core.models import AnalysisOutput, ChartSpec


class SQLiteConversationStore:
    """Legacy SQLite layout — compatibility only (ADR-007)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer_json TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    chart_json TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '',
                    strategy TEXT NOT NULL DEFAULT '',
                    session_frame_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            for statement in (
                "ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE messages ADD COLUMN strategy TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE messages ADD COLUMN session_frame_json TEXT NOT NULL DEFAULT '{}'",
            ):
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError:
                    pass

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
        frame_payload = json.dumps(session_frame or {}, default=str)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO messages(session_id,question,answer_json,rows_json,chart_json,provider,model,status,strategy,session_frame_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    question,
                    answer.model_dump_json(),
                    json.dumps(rows, default=str),
                    chart.model_dump_json() if chart else None,
                    provider,
                    model,
                    status,
                    strategy,
                    frame_payload,
                ),
            )

    def load(self, session_id: str, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT question,answer_json,rows_json,chart_json,provider,model,status,strategy,session_frame_json,created_at FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        loaded: list[dict] = []
        for row in reversed(rows):
            try:
                frame = json.loads(row[8] or "{}")
            except json.JSONDecodeError:
                frame = {}
            loaded.append(
                {
                    "question": row[0],
                    "answer": json.loads(row[1]),
                    "rows": json.loads(row[2]),
                    "chart_spec": json.loads(row[3]) if row[3] else None,
                    "provider": row[4],
                    "model": row[5],
                    "status": row[6] or "",
                    "strategy": row[7] or "",
                    "session_frame": frame if isinstance(frame, dict) else {},
                    "timestamp": row[9],
                }
            )
        return loaded

    def delete_session(self, session_id: str) -> int:
        session_id = (session_id or "").strip()
        if not session_id:
            return 0
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            return int(cursor.rowcount or 0)
