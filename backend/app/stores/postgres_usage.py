from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.platform_engine import get_session_factory
from app.db.platform_models import UsageEventRow


def _usage_day_bucket(session: Session, column):
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        return func.date(column)
    return func.date_trunc("day", column)


def _usage_day_iso(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "date") and callable(value.date):
        return value.date().isoformat()
    text = str(value)
    return text[:10]


class PostgresUsageStore:
    def __init__(
        self,
        database_url: str,
        *,
        workspace_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> None:
        self._session_factory = get_session_factory(database_url)
        self._workspace_id = workspace_id
        self._project_id = project_id

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
        with self._session_factory() as session:
            session.add(
                UsageEventRow(
                    workspace_id=self._workspace_id,
                    project_id=self._project_id,
                    request_id=request_id,
                    session_id=session_id,
                    provider=provider,
                    model=model,
                    strategy=strategy,
                    status=status,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total,
                    llm_calls=llm_calls,
                )
            )
            session.commit()

    def _since(self, days: int | None, mtd: bool) -> datetime | None:
        if mtd:
            now = datetime.now(timezone.utc)
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if days is not None and days > 0:
            return datetime.now(timezone.utc) - timedelta(days=days)
        return None

    def totals(self, *, days: int | None = 7, mtd: bool = False) -> dict[str, int]:
        since = self._since(days, mtd)
        with self._session_factory() as session:
            stmt = select(
                func.coalesce(func.sum(UsageEventRow.prompt_tokens), 0),
                func.coalesce(func.sum(UsageEventRow.completion_tokens), 0),
                func.coalesce(func.sum(UsageEventRow.total_tokens), 0),
                func.coalesce(func.sum(UsageEventRow.llm_calls), 0),
                func.count(),
            )
            if since:
                stmt = stmt.where(UsageEventRow.created_at >= since)
            row = session.execute(stmt).one()
        return {
            "prompt_tokens": int(row[0]),
            "completion_tokens": int(row[1]),
            "total_tokens": int(row[2]),
            "llm_calls": int(row[3]),
            "turns": int(row[4]),
        }

    def daily_totals(self, *, days: int = 7) -> list[dict[str, Any]]:
        since = self._since(days, False)
        with self._session_factory() as session:
            day_col = _usage_day_bucket(session, UsageEventRow.created_at)
            stmt = select(day_col, func.sum(UsageEventRow.total_tokens)).group_by(day_col).order_by(day_col)
            if since:
                stmt = stmt.where(UsageEventRow.created_at >= since)
            rows = session.execute(stmt).all()
        return [{"day": _usage_day_iso(r[0]), "tokens": int(r[1])} for r in rows]

    def by_model(self, *, days: int = 7) -> list[dict[str, Any]]:
        since = self._since(days, False)
        with self._session_factory() as session:
            stmt = (
                select(
                    UsageEventRow.provider,
                    UsageEventRow.model,
                    func.sum(UsageEventRow.total_tokens),
                    func.count(),
                )
                .group_by(UsageEventRow.provider, UsageEventRow.model)
                .order_by(func.sum(UsageEventRow.total_tokens).desc())
            )
            if since:
                stmt = stmt.where(UsageEventRow.created_at >= since)
            rows = session.execute(stmt).all()
        return [
            {"provider": r[0], "model": r[1], "tokens": int(r[2]), "turns": int(r[3])}
            for r in rows
        ]

    def list_events(self, *, days: int = 7, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        since = self._since(days, False)
        with self._session_factory() as session:
            stmt = select(UsageEventRow).order_by(UsageEventRow.created_at.desc()).limit(limit).offset(offset)
            if since:
                stmt = stmt.where(UsageEventRow.created_at >= since)
            rows = session.scalars(stmt).all()
        return [
            {
                "created_at": r.created_at.isoformat(),
                "request_id": r.request_id,
                "session_id": r.session_id,
                "provider": r.provider,
                "model": r.model,
                "strategy": r.strategy,
                "status": r.status,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "llm_calls": r.llm_calls,
            }
            for r in rows
        ]

    def export_csv(self, *, days: int = 30) -> str:
        events = self.list_events(days=days, limit=10_000, offset=0)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(events[0].keys()) if events else ["created_at"])
        writer.writeheader()
        for row in events:
            writer.writerow(row)
        return buf.getvalue()
