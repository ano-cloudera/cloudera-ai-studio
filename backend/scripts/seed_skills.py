#!/usr/bin/env python3
"""Idempotent seed for example workspace skills (draft versions)."""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.db.platform_engine import get_session_factory
from app.projects.bootstrap import DEFAULT_WORKSPACE_SLUG, ensure_platform_seed
from app.core.config import BACKEND_ROOT
from app.services.skill_service import SkillCreate, SkillService
from sqlalchemy import select
from app.db.platform_models import WorkspaceRow

SEED_SKILLS: tuple[dict, ...] = (
    {
        "key": "ask_data_analyst",
        "name": "Ask Data Analyst",
        "description": "Run governed Ask Data for analytical questions.",
        "config": {"handler_type": "ask_data"},
        "allowed_tools": ["ask_data"],
        "instructions": "Use governed metrics and explain caveats clearly.",
        "prompt_key": "ask_data.system",
    },
    {
        "key": "document_qa",
        "name": "Document Q&A",
        "description": "Answer from project knowledge libraries.",
        "config": {"handler_type": "rag"},
        "allowed_tools": ["rag_search", "document_retrieval"],
        "instructions": "Ground answers in retrieved evidence only.",
        "prompt_key": "rag.system",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed example workspace skills.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    url = (settings.database_url or "").strip()
    if settings.state_store.strip().lower() != "postgres" or not url:
        print("STATE_STORE=postgres and DATABASE_URL required", file=sys.stderr)
        return 1
    factory = get_session_factory(url)
    created = skipped = 0
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        workspace = session.execute(
            select(WorkspaceRow).where(WorkspaceRow.slug == DEFAULT_WORKSPACE_SLUG)
        ).scalar_one()
        svc = SkillService(session)
        for spec in SEED_SKILLS:
            if svc._find_skill_row(spec["key"], "workspace", workspace.id, None):
                skipped += 1
                continue
            if args.dry_run:
                print(f"would create skill key={spec['key']}")
                created += 1
                continue
            svc.create_skill(
                SkillCreate(
                    name=spec["name"],
                    key=spec["key"],
                    scope="workspace",
                    description=spec["description"],
                    workspace_id=workspace.id,
                    instructions=spec["instructions"],
                    prompt_key=spec["prompt_key"],
                    allowed_tools=spec["allowed_tools"],
                    config=spec["config"],
                )
            )
            created += 1
        if not args.dry_run:
            session.commit()
    print(f"seed_skills: created={created} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
