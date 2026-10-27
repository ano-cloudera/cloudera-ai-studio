"""SQLite usage store — legacy schema (M1 compatibility)."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.stores.protocols import GroupBy


class SQLiteUsageStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS llm_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    strategy TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    llm_calls INTEGER NOT NULL DEFAULT 0
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_created ON llm_usage_events(created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_model ON llm_usage_events(model)"
            )

    def record(
        self,
        *,
        request_id: str,
        session_id: str,
        provider: str,
        model: str,
        strategy: str,
        status: str,
        prompt_tokens: int,
        completion_tokens: int,
        llm_calls: int,
    ) -> None:
        total = prompt_tokens + completion_tokens
        if total <= 0 and llm_calls <= 0:
            return
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT INTO llm_usage_events(
                    created_at, request_id, session_id, provider, model, strategy, status,
                    prompt_tokens, completion_tokens, total_tokens, llm_calls
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ts,
                    request_id,
                    session_id,
                    provider,
                    model,
                    strategy,
                    status,
                    prompt_tokens,
                    completion_tokens,
                    total,
                    llm_calls,
                ),
            )

    def _since_clause(self, days: int | None, mtd: bool) -> tuple[str, list[Any]]:
        if mtd:
            now = datetime.now(timezone.utc)
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return "created_at >= ?", [start.isoformat()]
        if days is not None and days > 0:
            start = datetime.now(timezone.utc) - timedelta(days=days)
            return "created_at >= ?", [start.replace(microsecond=0).isoformat()]
        return "1=1", []

    def totals(self, *, days: int | None = 7, mtd: bool = False) -> dict[str, int]:
        where, params = self._since_clause(days, mtd)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                f"""SELECT
                    COALESCE(SUM(prompt_tokens), 0),
                    COALESCE(SUM(completion_tokens), 0),
                    COALESCE(SUM(total_tokens), 0),
                    COALESCE(SUM(llm_calls), 0),
                    COUNT(*)
                FROM llm_usage_events WHERE {where}""",
                params,
            ).fetchone()
        return {
            "prompt_tokens": int(row[0]),
            "completion_tokens": int(row[1]),
            "total_tokens": int(row[2]),
            "llm_calls": int(row[3]),
            "turns": int(row[4]),
        }

    def series(self, *, days: int = 7, group_by: GroupBy = "model") -> list[dict[str, Any]]:
        where, params = self._since_clause(days, False)
        sql = f"""
            SELECT substr(created_at, 1, 10) AS bucket,
                   provider || ' · ' || model AS label,
                   SUM(total_tokens) AS tokens
            FROM llm_usage_events WHERE {where}
            GROUP BY bucket, label ORDER BY bucket ASC, tokens DESC
        """
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [{"day": r[0], "label": r[1], "tokens": int(r[2])} for r in rows]

    def daily_totals(self, *, days: int = 7) -> list[dict[str, Any]]:
        where, params = self._since_clause(days, False)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""SELECT substr(created_at, 1, 10) AS day, SUM(total_tokens) AS tokens
                    FROM llm_usage_events WHERE {where}
                    GROUP BY day ORDER BY day ASC""",
                params,
            ).fetchall()
        return [{"day": r[0], "tokens": int(r[1])} for r in rows]

    def by_model(self, *, days: int = 7) -> list[dict[str, Any]]:
        where, params = self._since_clause(days, False)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""SELECT provider, model, SUM(total_tokens) AS tokens, COUNT(*) AS turns
                    FROM llm_usage_events WHERE {where}
                    GROUP BY provider, model ORDER BY tokens DESC""",
                params,
            ).fetchall()
        return [
            {"provider": r[0], "model": r[1], "tokens": int(r[2]), "turns": int(r[3])}
            for r in rows
        ]

    def list_events(self, *, days: int = 7, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        where, params = self._since_clause(days, False)
        params.extend([limit, offset])
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"""SELECT created_at, request_id, session_id, provider, model, strategy, status,
                           prompt_tokens, completion_tokens, total_tokens, llm_calls
                    FROM llm_usage_events WHERE {where}
                    ORDER BY id DESC LIMIT ? OFFSET ?""",
                params,
            ).fetchall()
        keys = (
            "created_at",
            "request_id",
            "session_id",
            "provider",
            "model",
            "strategy",
            "status",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "llm_calls",
        )
        return [dict(zip(keys, row)) for row in rows]

    def export_csv(self, *, days: int = 30) -> str:
        events = self.list_events(days=days, limit=10_000, offset=0)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(events[0].keys()) if events else ["created_at"])
        writer.writeheader()
        for row in events:
            writer.writerow(row)
        return buf.getvalue()
