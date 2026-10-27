#!/usr/bin/env python3
"""Build backend/data/local_gold_view_schemas.yaml from repo DDL + OSSIE fields."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import sqlglot
import yaml
from sqlglot import exp

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
OSSIE_PATH = BACKEND_ROOT / "projects" / "tempo_scan_impala" / "ossie" / "tempo_core.ossie.yaml"
OUT_PATH = BACKEND_ROOT / "data" / "local_gold_view_schemas.yaml"
SQL_GLOBS = (
    REPO_ROOT / "datasets" / "audit",
    REPO_ROOT / "datasets" / "gold",
)

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from validate_tempo_impala_contract import EXPECTED_SOURCES  # noqa: E402

CONTRACT_OSSIE_SOURCE_ALIASES: dict[str, str] = {
    "gold.rpt_sat_dc_month": "gold.rpt_sat_idm_dc_month",
    "gold.corr_b2b_sat_branch_month": "gold.corr_b2b_satidm_branch_month",
    "gold.corr_sat_dc_oos_material_month": "gold.corr_satidm_oos_material_month",
}


def _load_ossie_fields() -> dict[str, list[str]]:
    model = yaml.safe_load(OSSIE_PATH.read_text(encoding="utf-8"))
    by_source: dict[str, set[str]] = defaultdict(set)
    for dataset in model.get("datasets") or []:
        source = str(dataset.get("source") or "").strip().lower()
        if not source.startswith("gold."):
            continue
        for field in dataset.get("fields") or []:
            if isinstance(field, dict) and field.get("name"):
                by_source[source].add(str(field["name"]))
    return {key: sorted(values) for key, values in by_source.items()}


def _select_columns(select: exp.Select) -> list[str]:
    names: list[str] = []
    for projection in select.expressions:
        alias = projection.alias_or_name
        if alias:
            names.append(str(alias))
    return names


def _parse_create_views(text: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    cleaned = re.sub(r"--[^\n]*", "", text)
    chunks = re.split(r"(?=CREATE\s+VIEW\s+gold\.)", cleaned, flags=re.IGNORECASE)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.upper().startswith("CREATE VIEW"):
            continue
        if not chunk.rstrip().endswith(";"):
            chunk = chunk.rstrip() + ";"
        match = re.search(r"CREATE\s+VIEW\s+gold\.([a-zA-Z0-9_]+)", chunk, flags=re.IGNORECASE)
        if not match:
            continue
        view = f"gold.{match.group(1).lower()}"
        try:
            stmt = sqlglot.parse_one(chunk, read="hive")
        except Exception:
            continue
        select = stmt.find(exp.Select)
        if not select:
            continue
        cols = _select_columns(select)
        if cols:
            found[view] = cols
    return found


def _scan_sql_ddl() -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for base in SQL_GLOBS:
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.sql")):
            merged.update(_parse_create_views(path.read_text(encoding="utf-8", errors="replace")))
    return merged


def _resolve_columns(contract_source: str, ddl: dict[str, list[str]], ossie: dict[str, list[str]]) -> tuple[list[str], bool]:
    key = contract_source.lower()
    if key in ddl:
        return ddl[key], True
    ossie_key = CONTRACT_OSSIE_SOURCE_ALIASES.get(key, key)
    if ossie_key in ddl:
        return ddl[ossie_key], True
    if key in ossie:
        return ossie[key], False
    if ossie_key in ossie:
        return ossie[ossie_key], False
    return [], False


def main() -> int:
    ddl = _scan_sql_ddl()
    ossie = _load_ossie_fields()
    views: dict[str, object] = {}
    missing: list[str] = []
    for source in sorted(EXPECTED_SOURCES, key=str.lower):
        key = source.lower()
        columns, from_ddl = _resolve_columns(key, ddl, ossie)
        if not columns:
            missing.append(source)
            continue
        views[key] = {
            "columns": columns,
            "ossie_source": CONTRACT_OSSIE_SOURCE_ALIASES.get(key, key),
            "from_ddl": from_ddl,
        }
    payload = {
        "version": 1,
        "description": "Output column names for OSSIE/Impala gold views (local DuckDB tables).",
        "views": views,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(views)} views)")
    ddl_count = sum(1 for v in views.values() if v.get("from_ddl"))
    print(f"  from DDL: {ddl_count}, from OSSIE fields only: {len(views) - ddl_count}")
    if missing:
        print("Missing column definitions:", ", ".join(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
