#!/usr/bin/env python3
"""Idempotent import of legacy file prompts into Postgres (draft versions only)."""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.db.platform_engine import get_session_factory
from app.prompt_management.keys import ASK_DATA_SYSTEM, RAG_INSUFFICIENT_EVIDENCE, RAG_SYSTEM
from app.prompt_management.sources import FilePromptSource
from app.services.prompt_service import PromptCreate, PromptService

SEED_ROWS: tuple[tuple[str, str], ...] = (
    (ASK_DATA_SYSTEM, "Ask Data system prompt"),
    (RAG_SYSTEM, "RAG system prompt"),
    (RAG_INSUFFICIENT_EVIDENCE, "RAG insufficient evidence message"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed global prompt rows from legacy files (no overwrite).")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing.")
    args = parser.parse_args()
    settings = get_settings()
    url = (settings.database_url or "").strip()
    if settings.state_store.strip().lower() != "postgres" or not url:
        print("STATE_STORE=postgres and DATABASE_URL required", file=sys.stderr)
        return 1
    files = FilePromptSource()
    factory = get_session_factory(url)
    created = 0
    skipped = 0
    with factory() as session:
        svc = PromptService(session)
        for key, name in SEED_ROWS:
            if svc._find_prompt_row(key, "global", None, None):
                skipped += 1
                continue
            content = files.get(key) or f"# {name}\n"
            if args.dry_run:
                print(f"would create global prompt key={key}")
                created += 1
                continue
            svc.create_prompt(
                PromptCreate(
                    name=name,
                    key=key,
                    scope="global",
                    description="Seeded from legacy file prompt source",
                    initial_content=content,
                    created_by="seed_prompts.py",
                )
            )
            created += 1
        if not args.dry_run:
            session.commit()
    print(f"seed_prompts: created={created} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
