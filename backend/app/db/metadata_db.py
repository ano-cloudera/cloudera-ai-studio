"""Platform metadata database URL helpers (PostgreSQL + SQLite)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from app.core.config import Settings


def normalize_database_url(url: str) -> str:
    return (url or "").strip()


def metadata_dialect_name(url: str) -> str | None:
    raw = normalize_database_url(url)
    if not raw:
        return None
    scheme = urlparse(raw.replace("+", " ", 1).replace(" ", "+")).scheme.lower()
    if scheme.startswith("postgresql") or scheme == "postgres":
        return "postgresql"
    if scheme.startswith("sqlite"):
        return "sqlite"
    return scheme.split("+", 1)[0] if scheme else None


def is_sqlite_metadata_url(url: str) -> bool:
    return metadata_dialect_name(url) == "sqlite"


def is_postgresql_metadata_url(url: str) -> bool:
    return metadata_dialect_name(url) == "postgresql"


def platform_metadata_configured(settings: Settings) -> bool:
    url = normalize_database_url(settings.database_url)
    if not url:
        return False
    return metadata_dialect_name(url) in {"postgresql", "sqlite"}


def sqlite_metadata_path_from_url(url: str) -> str | None:
    """Return filesystem path for file-backed SQLite URLs (for guards/docs)."""
    if not is_sqlite_metadata_url(url):
        return None
    parsed = urlparse(url)
    if parsed.path and parsed.path not in {"/", ""}:
        path = parsed.path
        if path.startswith("//"):
            return path[1:]
        if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
            return path[1:]
        return path
    if parsed.netloc:
        return parsed.netloc
    return None


def configured_uvicorn_workers() -> int:
    raw = (os.environ.get("UVICORN_WORKERS") or os.environ.get("WEB_CONCURRENCY") or "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def validate_sqlite_single_worker(url: str) -> None:
    if is_sqlite_metadata_url(url) and configured_uvicorn_workers() > 1:
        raise RuntimeError(
            "SQLite platform metadata requires a single backend process "
            "(set UVICORN_WORKERS=1; do not run multiple uvicorn workers)."
        )
