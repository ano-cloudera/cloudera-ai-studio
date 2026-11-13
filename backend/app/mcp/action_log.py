"""The record of actions a person approved: what was run, on which server, with which arguments, when, and what came back.

The platform writes it when an approved action runs (success or failure), whichever MCP server it was sent to, so the history is
the same for any action and does not depend on what a server keeps. It is a persistent ordered store (diskcache Index) next to
the answer cache in the project storage: no expiry and no eviction, since it is an audit trail, and one small entry per action.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RESULT_LIMIT = 4000
_lock = threading.Lock()
_stores: dict[str, Any] = {}


def _directory(settings: Any) -> Path | None:
    from app.ask_data.answer_cache import cache_directory

    answers = cache_directory(settings)
    return Path(answers).parent / "actions" if answers is not None else None


def _store(settings: Any) -> Any:
    """The Index for this deployment, or an in-memory dict when there is no project storage."""
    directory = _directory(settings)
    key = str(directory)
    with _lock:
        if key not in _stores:
            try:
                import diskcache

                if directory is None:
                    raise OSError("no project storage")
                directory.mkdir(parents=True, exist_ok=True)
                _stores[key] = diskcache.Index(str(directory))
            except Exception:  # noqa: BLE001 - kept in memory for this process rather than not at all
                logger.warning("action_log_disk_unavailable")
                _stores[key] = {}
        return _stores[key]


def record(
    settings: Any,
    *,
    server_id: str,
    server: str,
    tool: str,
    title: str | None,
    arguments: dict[str, Any],
    ok: bool,
    result: str = "",
    error: str = "",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "at": now.isoformat(timespec="seconds"),
        "server_id": server_id,
        "server": server,
        "tool": tool,
        "title": (title or tool).strip()[:200],
        "arguments": arguments,
        "status": "ok" if ok else "failed",
        "result": result[:RESULT_LIMIT],
        "error": error[:600],
    }
    try:
        _store(settings)[f"{now.strftime('%Y%m%d%H%M%S%f')}-{entry['id']}"] = entry  # sorts by time
    except Exception:  # noqa: BLE001 - the action already ran; a failed record must not turn that into an error
        logger.exception("action_log_write_failed")
    return entry


def history(settings: Any, *, limit: int = 200) -> list[dict[str, Any]]:
    """The recorded actions, newest first."""
    try:
        store = _store(settings)
        keys = sorted(store.keys(), reverse=True)[: max(1, min(1000, limit))]
        return [store[key] for key in keys]
    except Exception:  # noqa: BLE001
        logger.exception("action_log_read_failed")
        return []


def count(settings: Any) -> int:
    try:
        return len(_store(settings))
    except Exception:  # noqa: BLE001
        return 0


def clear_memory() -> None:
    with _lock:
        _stores.clear()
