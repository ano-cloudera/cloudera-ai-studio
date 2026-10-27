#!/usr/bin/env python3
"""CAI deployment preflight — validate config without starting the full stack."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

SECRET_NAME_RE = re.compile(r"(password|secret|api_key|token)", re.I)


def _load_settings():
    from app.core.config import get_settings

    get_settings.cache_clear()
    return get_settings()


def _check_paths(settings) -> list[str]:
    errors: list[str] = []
    for label, path in (
        ("document_storage_root", settings.document_storage_root),
        ("semantic_runtime_storage_root", settings.semantic_runtime_storage_root),
    ):
        p = Path(path)
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".preflight_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"{label} not writable: {p} ({exc})")
    url = (settings.database_url or "").strip()
    if url.startswith("sqlite"):
        from app.db.metadata_db import sqlite_metadata_path_from_url

        fs = sqlite_metadata_path_from_url(url)
        if fs:
            parent = Path(fs).expanduser().resolve().parent
            try:
                parent.mkdir(parents=True, exist_ok=True)
                if not os.access(parent, os.W_OK):
                    errors.append(f"metadata directory not writable: {parent}")
            except OSError as exc:
                errors.append(f"metadata directory error: {parent} ({exc})")
    return errors


def _check_workers(settings) -> list[str]:
    from app.db.metadata_db import configured_uvicorn_workers, is_sqlite_metadata_url

    workers = configured_uvicorn_workers()
    url = (settings.database_url or "").strip()
    if is_sqlite_metadata_url(url) and workers > 1:
        return [f"SQLite metadata requires UVICORN_WORKERS=1 (got {workers})"]
    return []


def _check_qdrant_url(settings) -> list[str]:
    raw = (settings.qdrant_url or "").strip()
    if not raw:
        return []  # optional unless RAG required at runtime
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return [f"QDRANT_URL malformed: {raw!r}"]
    return []


def _check_cors(settings) -> list[str]:
    if not (settings.cors_origins or "").strip():
        return ["CORS_ORIGINS empty — browser FE will fail cross-origin unless same-origin proxy"]
    if "*" in settings.cors_origins:
        return ["CORS_ORIGINS contains wildcard — avoid for CAI unless explicitly approved"]
    return []


def _check_frontend_urls() -> list[str]:
    errors: list[str] = []
    be = os.environ.get("BACKEND_API_URL", "").strip()
    pub = os.environ.get("NEXT_PUBLIC_BACKEND_URL", "").strip()
    if not be:
        errors.append("BACKEND_API_URL not set (required for production frontend proxy)")
    elif be.startswith("http://127.0.0.1") or be.startswith("http://localhost"):
        errors.append("BACKEND_API_URL uses localhost — set service hostname for CAI split deploy")
    if pub and ("127.0.0.1" in pub or "localhost" in pub):
        errors.append("NEXT_PUBLIC_BACKEND_URL uses localhost — set public backend URL for CAI")
    return errors


def _scan_example_secrets() -> list[str]:
    """Ensure deployment examples do not contain literal secret assignments."""
    hits: list[str] = []
    allowlist = {
        ROOT / "deployment/profiles/cai.env.example",
        ROOT / "deployment/profiles/cai.env",
    }
    paths = [p for p in allowlist if p.is_file()]
    if not paths:
        paths = list((ROOT / "deployment/profiles").glob("*.example"))
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            if SECRET_NAME_RE.search(key) and val.strip() and val.strip() not in {"", '""', "''"}:
                if "env://" in val or "<" in val or "your-" in val.lower():
                    continue
                if val.strip().endswith("_PASSWORD") or val.strip() == "m1pass":
                    continue
                hits.append(f"{path.relative_to(ROOT)}:{i} suspicious secret literal")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="CAI deployment preflight")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings (localhost URLs, CORS)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    settings = _load_settings()
    from app.platform.readiness import validate_startup_config

    errors: list[str] = []
    warnings: list[str] = []
    try:
        validate_startup_config(settings)
    except RuntimeError as exc:
        errors.append(str(exc))

    errors.extend(_check_paths(settings))
    errors.extend(_check_workers(settings))
    warnings.extend(_check_qdrant_url(settings))
    warnings.extend(_check_cors(settings))
    if args.strict:
        warnings.extend(_check_frontend_urls())
    else:
        _check_frontend_urls()  # report only in json

    fe_warnings = _check_frontend_urls()
    secret_hits = _scan_example_secrets()

    if secret_hits:
        errors.extend(secret_hits)

    report = {
        "cai_data_dir": os.environ.get("CAI_DATA_DIR"),
        "database_url_set": bool((settings.database_url or "").strip()),
        "uvicorn_workers": os.environ.get("UVICORN_WORKERS", "1"),
        "qdrant_url": (settings.qdrant_url or "")[:80],
        "document_storage_root": str(settings.document_storage_root),
        "semantic_runtime_storage_root": str(settings.semantic_runtime_storage_root),
        "errors": errors,
        "warnings": warnings + fe_warnings,
        "ok": not errors and (not args.strict or not (warnings + fe_warnings)),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
