#!/usr/bin/env python3
"""Create OSSIE Section 3 gold.*_semantic views on live Impala (from repo .env)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.impala_backend import ImpalaBackend  # noqa: E402

SQL_PATH = REPO / "datasets/migration/deploy_gold_semantic_section3.sql"


def main() -> int:
    raw_lines = [
        line
        for line in SQL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    text = "\n".join(raw_lines)
    statements = [
        block.strip()
        for block in re.split(r";\s*\n", text)
        if block.strip().upper().startswith("CREATE VIEW")
    ]
    get_settings.cache_clear()
    backend = ImpalaBackend(get_settings())
    for stmt in statements:
        if not stmt.rstrip().endswith(";"):
            stmt += ";"
        match = re.search(r"CREATE VIEW IF NOT EXISTS gold\.([a-z0-9_]+)", stmt, re.I)
        name = match.group(1) if match else "?"
        print(f"Creating gold.{name} ...", flush=True)
        backend.query(stmt)
        print(f"  OK gold.{name}")
    print("Done. Verify: SELECT COUNT(*) FROM gold.rpt_sap_material_month_semantic;")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
