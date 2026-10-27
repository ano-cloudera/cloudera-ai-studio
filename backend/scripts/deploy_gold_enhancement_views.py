#!/usr/bin/env python3
"""Deploy optional enhancement Gold views from datasets/gold/*.sql (read CREATE VIEW blocks)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.impala_backend import ImpalaBackend  # noqa: E402

GOLD_DIR = REPO / "datasets" / "gold"
DEFAULT_FILES = (
    "01_corr_b2b_branch_material_month.sql",
    "02_rpt_sat_promo_b2b_sellout_uplift.sql",
    "03_corr_service_sales_office_cust_group_material_month.sql",
)


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
        match = re.search(r"CREATE VIEW gold\.([a-z0-9_]+)", stmt, re.I)
        out.append((match.group(1) if match else "?", stmt))
    return out


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = names if names else list(DEFAULT_FILES)
    get_settings.cache_clear()
    backend = ImpalaBackend(get_settings())
    ok, failed, skipped = 0, 0, 0
    for filename in files:
        path = GOLD_DIR / filename
        if not path.is_file():
            print(f"Skip missing {path}", file=sys.stderr)
            skipped += 1
            continue
        for view_name, stmt in _statements(path.read_text(encoding="utf-8")):
            print(f"Creating gold.{view_name} ...", flush=True)
            try:
                backend.query(stmt)
                print(f"  OK gold.{view_name}")
                ok += 1
            except Exception as exc:
                failed += 1
                print(f"  FAIL gold.{view_name}: {exc}", file=sys.stderr)
    print(f"Done: {ok} ok, {failed} failed, {skipped} files skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
