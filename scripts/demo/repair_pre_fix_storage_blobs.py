#!/usr/bin/env python3
"""Copy Knowledge blobs from pre-fix backend/backend/storage into canonical storage root."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select

from app.core.config import get_settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import DocumentRow
from app.storage.object_store import build_object_store

ORPHAN_ROOT = ROOT / "backend" / "backend" / "runtime" / "document_storage"
EVIDENCE = ROOT / "testing" / "evidence" / "knowledge-ingestion-recovery" / "orphan-storage-repair.json"


def main() -> int:
    if not ORPHAN_ROOT.is_dir():
        print("no orphan storage tree", ORPHAN_ROOT)
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps({"repaired": 0, "orphan_root_missing": True}, indent=2) + "\n")
        return 0

    settings = get_settings()
    store = build_object_store(settings.document_storage_root)
    factory = get_session_factory(settings.database_url)
    repaired: list[dict] = []
    with factory() as session:
        rows = session.execute(select(DocumentRow)).scalars().all()
        for row in rows:
            if store.exists(row.storage_path):
                continue
            src = ORPHAN_ROOT / row.storage_path
            if not src.is_file():
                continue
            store.put(row.storage_path, src.read_bytes())
            repaired.append(
                {
                    "document_id": str(row.id),
                    "storage_path": row.storage_path,
                    "status": row.status,
                }
            )
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps({"repaired": len(repaired), "items": repaired, "orphan_root": str(ORPHAN_ROOT)}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"repaired {len(repaired)} blobs → {settings.document_storage_root}")
    print(f"wrote {EVIDENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
