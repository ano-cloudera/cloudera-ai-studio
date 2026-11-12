"""Answers kept on disk (diskcache, a SQLite file under the project storage), so they survive a restart.

The key is the question as written out in full from the conversation (a follow-up such as "and per province?" is keyed by its
rewritten form, never by its own words), the semantic model version, how the question is understood, the language model and
whether the agent answered. Three modes (setting ANSWER_CACHE):

* "fallback" (default): every question is answered live; the last answer to the same question is served only when the live
  answer fails (the data source or its metastore is down), with a note saying when it was computed.
* "first": a recent answer (ANSWER_CACHE_TTL_SECONDS) to the same question is served straight away. For demos, after the demo
  questions were asked once (the judge does that).
* "off": nothing is kept.

Only successful governed or agent answers are kept. Without diskcache installed the cache lives in memory.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STALE_LIMIT_SECONDS = 7 * 24 * 3600  # how old an answer may be to stand in when the data source fails
CACHEABLE_STRATEGIES = {"governed", "agent", "sql_fallback"}


@lru_cache(maxsize=1)
def code_version() -> str:
    """The commit the Backend runs, so an update (the 'Update from GitHub' job) never serves an answer an older version made."""
    root = Path(__file__).resolve().parents[3]
    try:
        head = (root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = root / ".git" / head[5:]
            if ref.exists():
                return ref.read_text(encoding="utf-8").strip()
            packed = root / ".git" / "packed-refs"
            for line in packed.read_text(encoding="utf-8").splitlines() if packed.exists() else []:
                if line.endswith(head[5:]):
                    return line.split()[0]
        return head
    except OSError:
        return os.environ.get("ACCELERATOR_VERSION", "")


def _normalise(question: str) -> str:
    return " ".join((question or "").casefold().split()).rstrip("?.! ")


class AnswerCache:
    def __init__(self, directory: Path | None, *, mode: str = "fallback", ttl_seconds: int = 21600) -> None:
        self.mode = (mode or "fallback").strip().lower()
        self.ttl_seconds = ttl_seconds
        self._memory: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._store = None
        if self.mode == "off" or directory is None:
            return
        try:
            import diskcache

            directory.mkdir(parents=True, exist_ok=True)
            self._store = diskcache.Cache(str(directory), size_limit=256 * 1024 * 1024)
        except Exception:  # noqa: BLE001 - an in-memory cache is still better than none
            logger.warning("answer_cache_disk_unavailable directory=%s", directory)

    @property
    def enabled(self) -> bool:
        return self.mode in {"fallback", "first"}

    @staticmethod
    def key(question: str, scope: dict[str, Any]) -> str:
        raw = json.dumps({"q": _normalise(question), "code": code_version(), **scope}, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _get(self, key: str) -> dict[str, Any] | None:
        try:
            if self._store is not None:
                value = self._store.get(key)
            else:
                with self._lock:
                    value = self._memory.get(key)
        except Exception:  # noqa: BLE001 - a broken cache never breaks a question
            logger.warning("answer_cache_read_failed")
            return None
        return value if isinstance(value, dict) else None

    def put(self, key: str, response: Any, frame: dict[str, Any] | None = None) -> None:
        if not self.enabled or getattr(response, "status", "") != "SUCCESS" or getattr(response, "strategy", "") not in CACHEABLE_STRATEGIES:
            return
        value = {
            "response": response.model_dump(mode="json"),
            "frame": frame or None,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            if self._store is not None:
                self._store.set(key, value, expire=max(STALE_LIMIT_SECONDS, self.ttl_seconds))
            else:
                with self._lock:
                    self._memory[key] = value
        except Exception:  # noqa: BLE001
            logger.warning("answer_cache_write_failed")

    def _age(self, value: dict[str, Any]) -> float:
        try:
            stored = datetime.fromisoformat(str(value.get("stored_at")))
        except ValueError:
            return float("inf")
        return (datetime.now(timezone.utc) - stored).total_seconds()

    def recent(self, key: str) -> dict[str, Any] | None:
        """A fresh answer to serve straight away (mode "first" only)."""
        if self.mode != "first":
            return None
        value = self._get(key)
        return value if value and self._age(value) <= self.ttl_seconds else None

    def stand_in(self, key: str) -> dict[str, Any] | None:
        """The last answer, to serve when the live one failed (modes "fallback" and "first")."""
        if not self.enabled:
            return None
        value = self._get(key)
        return value if value and self._age(value) <= STALE_LIMIT_SECONDS else None


def cache_directory(settings: Any) -> Path | None:
    """ANSWER_CACHE_DIR, else next to the platform SQLite database (the project storage in Cloudera AI), else CAI_DATA_DIR."""
    explicit = str(getattr(settings, "answer_cache_dir", "") or "").strip()
    if explicit:
        return Path(explicit)
    url = str(getattr(settings, "database_url", "") or "")
    if url.startswith("sqlite") and ":///" in url:
        db = Path(url.split(":///", 1)[1])
        return db.parent.parent / "cache" / "answers"
    data_dir = getattr(settings, "cai_data_dir", None)
    return Path(data_dir) / "cache" / "answers" if data_dir else None


def served_note(value: dict[str, Any], reason: str, language: str) -> str:
    stamp = str(value.get("stored_at") or "")[:16].replace("T", " ")
    if reason == "data_source_unavailable":
        return (
            f"Sumber data sedang tidak bisa dijangkau, jadi ini jawaban yang dihitung pada {stamp} UTC untuk pertanyaan yang sama."
            if language == "id"
            else f"The data source cannot be reached right now, so this is the answer computed at {stamp} UTC for the same question."
        )
    return ""
