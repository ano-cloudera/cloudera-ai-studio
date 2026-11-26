"""Semantic drafts run in the background: profiling and drafting several tables takes longer than a browser or the platform's proxy
waits for one request. The Backend runs one process, so the jobs live in memory; a restart forgets them, and the user starts again.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.connectors.errors import ConnectorError
from app.connectors.service import ConnectorRegistryService
from app.connectors.discovery import MetadataDiscoveryService
from app.connectors.sql_compose import qualified_table_sql
from app.core.config import Settings
from app.semantic_registry.semantic_draft import DraftTable, draft_model, slug
from app.semantic_registry.table_profile import profile_table

logger = logging.getLogger(__name__)

KEEP_SECONDS = 1800
MAX_TABLES = 12


@dataclass
class DraftJob:
    id: str
    owner: str = ""  # the project that started it; another project cannot read it
    status: str = "running"  # running | done | failed
    stage: str = "Starting"
    result: dict | None = None
    error: str | None = None
    started: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "elapsed_seconds": round(time.monotonic() - self.started),
            "result": self.result,
            "error": self.error,
        }


class DraftJobs:
    def __init__(self) -> None:
        self._jobs: dict[str, DraftJob] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, work: Callable[[Callable[[str], None]], Awaitable[dict]], *, owner: str = "") -> DraftJob:
        self._forget_old()
        job = DraftJob(id=uuid.uuid4().hex, owner=owner)
        self._jobs[job.id] = job

        def say(stage: str) -> None:
            job.stage = stage

        async def runner() -> None:
            try:
                job.result = await work(say)
                job.status = "done"
                job.stage = "Done"
            except DraftError as exc:
                job.status, job.error = "failed", str(exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("semantic_draft_failed")
                job.status, job.error = "failed", f"The draft failed: {type(exc).__name__}"

        task = asyncio.get_running_loop().create_task(runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def get(self, job_id: str, *, owner: str = "") -> DraftJob | None:
        job = self._jobs.get(job_id)
        return job if job is not None and job.owner == owner else None

    def _forget_old(self) -> None:
        now = time.monotonic()
        for key in [k for k, j in self._jobs.items() if j.status != "running" and now - j.started > KEEP_SECONDS]:
            del self._jobs[key]


DRAFT_JOBS = DraftJobs()


class DraftError(RuntimeError):
    """A failure the user can act on; its text is shown as it is."""


def split_qualified(qualified: str, default_catalog: str | None, default_schema: str | None) -> tuple[str | None, str | None, str]:
    parts = [p for p in qualified.strip().split(".") if p]
    if len(parts) >= 3:
        return parts[-3], parts[-2], parts[-1]
    if len(parts) == 2:
        return default_catalog, parts[0], parts[1]
    return default_catalog, default_schema, parts[0] if parts else ""


def profile_tables(
    session_factory: Callable[[], Any],
    settings: Settings,
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    tables: list[str],
    say: Callable[[str], None],
) -> list[DraftTable]:
    """Describe and profile each selected table (blocking: run it in a thread)."""
    with session_factory() as session:
        registry = ConnectorRegistryService(session, settings=settings)
        try:
            row = registry.get_connector(connection_id, workspace_id=workspace_id, project_id=project_id)
            adapter = registry.build_adapter(row)
        except ConnectorError as exc:
            raise DraftError(exc.message) from exc
        connector_type = row.connector_type
        discovery = MetadataDiscoveryService(registry, settings=settings)
        default_catalog, default_schema = adapter.default_context()
        described = []
        for qualified in tables[:MAX_TABLES]:
            catalog, schema, table = split_qualified(qualified, default_catalog, default_schema)
            try:
                detail = discovery.describe_table(connection_id, workspace_id=workspace_id, project_id=project_id, catalog=catalog, schema=schema, table=table)
            except ConnectorError as exc:
                raise DraftError(f"{qualified}: {exc.message}") from exc
            described.append((catalog, schema, table, detail))

    def run(sql: str, max_rows: int) -> list[dict]:
        return adapter.execute_readonly_query(sql, max_rows=max_rows).rows

    done = 0

    def one(item) -> DraftTable:
        nonlocal done
        catalog, schema, table, detail = item
        profile = profile_table(
            run,
            connector_type=connector_type,
            catalog=catalog,
            schema=schema,
            table=table,
            table_sql=qualified_table_sql(connector_type=connector_type, catalog=catalog, schema=schema, table=table),
            columns=detail.columns,
            primary_key=detail.primary_key,
            comment=detail.comment,
        )
        done += 1
        say(f"Profiled {done} of {len(described)} table(s)")
        return DraftTable(key=slug(table, "table"), connection_id=str(connection_id), profile=profile, run=run)

    say(f"Reading {len(described)} table(s) from the data source")
    with ThreadPoolExecutor(max_workers=3) as pool:
        drafted = list(pool.map(one, described))
    keys: set[str] = set()
    for table in drafted:  # two schemas can hold a table of the same name
        base, n = table.key, 2
        while table.key in keys:
            table.key = f"{base}_{n}"
            n += 1
        keys.add(table.key)
    return drafted


async def run_draft(
    say: Callable[[str], None],
    *,
    settings: Settings,
    session_factory: Callable[[], Any],
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    tables: list[str],
    language: str,
    context: str,
    resolve_provider: Callable[[], tuple[Any, str] | None],
) -> dict:
    resolved = resolve_provider()
    if resolved is None:
        raise DraftError("No AI model is available to draft with. Assign one to Ask Data in Settings → AI Models, then try again.")
    provider, label = resolved
    drafted = await asyncio.to_thread(
        profile_tables,
        session_factory,
        settings,
        workspace_id=workspace_id,
        project_id=project_id,
        connection_id=connection_id,
        tables=tables,
        say=say,
    )
    if not drafted:
        raise DraftError("No table was selected.")
    result = await draft_model(provider, drafted, language=language, context=context, provider_label=label, progress=say)
    return result.to_dict()
