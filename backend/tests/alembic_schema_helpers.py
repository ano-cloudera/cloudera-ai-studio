from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_alembic_head(database_url: str | None = None) -> None:
    """Apply Alembic migrations through head (preferred over Base.metadata.create_all)."""
    url = database_url or os.environ.get("DATABASE_URL") or ""
    if not url:
        raise RuntimeError("DATABASE_URL required for Alembic test bootstrap")
    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def ensure_platform_schema_via_alembic(engine: Engine) -> None:
    ensure_alembic_head(str(engine.url))


def clear_model_assignments(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM model_assignments"))
