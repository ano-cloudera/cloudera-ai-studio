#!/usr/bin/env python3
"""Deploy gold views from datasets/migration/deploy_gold_views_lengkap.sql."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.impala_backend import ImpalaBackend  # noqa: E402

SQL_PATH = REPO / "datasets/migration/deploy_gold_views_lengkap.sql"


def _statements(text: str) -> list[tuple[str, str]]:
    lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("--")]
    body = "\n".join(lines)
    out: list[tuple[str, str]] = []
    for block in re.split(r";\s*\n", body):
        stmt = block.strip()
        if not stmt.upper().startswith("CREATE VIEW"):
            continue
        if not stmt.rstrip().endswith(";"):
            stmt += ";"
        match = re.search(r"CREATE VIEW IF NOT EXISTS gold\.([a-z0-9_]+)", stmt, re.I)
        out.append((match.group(1) if match else "?", stmt))
    return out


def main() -> int:
    statements = _statements(SQL_PATH.read_text(encoding="utf-8"))
    get_settings.cache_clear()
    backend = ImpalaBackend(get_settings())
    ok, failed = 0, 0
    for name, stmt in statements:
        print(f"Creating gold.{name} ...", flush=True)
        try:
            backend.query(stmt)
            print(f"  OK gold.{name}")
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"  FAIL gold.{name}: {exc}", file=sys.stderr)
    print(f"Done: {ok} ok, {failed} failed (total {len(statements)})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
