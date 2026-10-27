#!/usr/bin/env python3
"""Controlled demo/test application-data cleanup for standalone Cloudera AI Studio.

Default mode is dry-run. Use --apply --confirm-local-db to mutate metadata only
(never external Impala/PostgreSQL business databases).
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.chat.attachments.constants import CHAT_ATTACHMENTS_LIBRARY_NAME  # noqa: E402
from app.connectors.service import ConnectorRegistryService  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db.platform_engine import get_session_factory  # noqa: E402
from app.db.platform_models import (  # noqa: E402
    AiModelRow,
    AiProviderRow,
    ConnectorRow,
    ConversationRow,
    LibraryRow,
    MessageRow,
    ModelAssignmentRow,
    ModelTestRunRow,
    ProjectRow,
    PromptRow,
    SemanticModelRow,
    SemanticRuntimeDeploymentRow,
    SemanticRuntimeStateRow,
    SkillRow,
    UsageEventRow,
    WorkspaceRow,
)
from app.prompt_management.keys import KNOWN_PROMPT_KEYS  # noqa: E402
from app.projects.bootstrap import DEFAULT_PROJECT_SLUG  # noqa: E402
from app.services.library_service import LibraryService  # noqa: E402

Classification = Literal["A", "B", "C", "D"]

BASELINE_SKILL_KEYS = frozenset({"ask_data_analyst", "document_qa"})

@dataclass
class CleanupPlan:
    libraries: list[dict[str, Any]] = field(default_factory=list)
    semantic_models: list[dict[str, Any]] = field(default_factory=list)
    connectors: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    conversations: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    unknown: list[dict[str, Any]] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _db_identity(settings: Settings) -> str:
    url = (settings.database_url or "").strip()
    if "@" in url:
        return url.split("@", 1)[1]
    return url or "(empty)"


def assert_safe_environment(settings: Settings, *, apply: bool) -> None:
    root = str(ROOT.resolve())
    if "enterprise-ai-poc" in root:
        raise SystemExit("Refusing: script must run from cloudera-ai-studio only.")
    url = (settings.database_url or "").lower()
    if settings.state_store.strip().lower() != "postgres" or not url:
        raise SystemExit("Requires STATE_STORE=postgres and DATABASE_URL.")
    if apply:
        allowed_hosts = ("127.0.0.1", "localhost")
        if not any(h in url for h in allowed_hosts):
            raise SystemExit(f"Refusing --apply: DATABASE_URL host must be local ({allowed_hosts}).")
        if "enterprise-ai-poc" in url:
            raise SystemExit("Refusing --apply: DATABASE_URL must not reference enterprise-ai-poc.")


def preserved_project_slugs(settings: Settings) -> set[str]:
    slug = (settings.default_project_slug or DEFAULT_PROJECT_SLUG).strip()
    return {slug}


def classify_library(row: LibraryRow) -> Classification:
    if row.name == CHAT_ATTACHMENTS_LIBRARY_NAME:
        return "A"
    return "C"


def classify_prompt(row: PromptRow) -> Classification:
    if row.scope == "global" and row.key in KNOWN_PROMPT_KEYS:
        return "A"
    return "C"


def classify_skill(row: SkillRow) -> Classification:
    if row.scope == "workspace" and row.key in BASELINE_SKILL_KEYS:
        return "A"
    return "C"


def classify_connector(row: ConnectorRow) -> Classification:
    return "C"


def classify_semantic(row: SemanticModelRow) -> Classification:
    return "C"


def classify_project(row: ProjectRow, preserved: set[str]) -> Classification:
    if row.slug in preserved:
        return "A"
    return "C"


def collect_inventory(session: Session, settings: Settings) -> dict[str, Any]:
    preserved = preserved_project_slugs(settings)
    ws = session.execute(select(WorkspaceRow).limit(1)).scalar_one()
    projects = list(session.execute(select(ProjectRow).order_by(ProjectRow.slug)).scalars().all())
    inv: dict[str, Any] = {
        "captured_at": _utc_now(),
        "database": _db_identity(settings),
        "repo_root": str(ROOT.resolve()),
        "workspace_slug": ws.slug,
        "preserved_project_slugs": sorted(preserved),
        "counts": {},
        "records": {},
    }
    libs = list(session.execute(select(LibraryRow)).scalars().all())
    models = list(session.execute(select(SemanticModelRow)).scalars().all())
    connectors = list(session.execute(select(ConnectorRow)).scalars().all())
    prompts = list(session.execute(select(PromptRow)).scalars().all())
    skills = list(session.execute(select(SkillRow)).scalars().all())
    conv_count = session.execute(select(func.count()).select_from(ConversationRow)).scalar() or 0

    inv["counts"] = {
        "projects": len(projects),
        "libraries": len(libs),
        "chat_attachment_libraries": sum(1 for l in libs if l.name == CHAT_ATTACHMENTS_LIBRARY_NAME),
        "semantic_models": len(models),
        "connectors": len(connectors),
        "prompts": len(prompts),
        "skills": len(skills),
        "conversations": int(conv_count),
    }
    by_class: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def bump(kind: str, cls: Classification) -> None:
        by_class[kind][cls] += 1

    inv["records"]["libraries"] = []
    for row in libs:
        cls = classify_library(row)
        bump("libraries", cls)
        inv["records"]["libraries"].append(
            {"id": str(row.id), "name": row.name, "project_id": str(row.project_id), "class": cls}
        )
    inv["records"]["semantic_models"] = []
    for row in models:
        cls = classify_semantic(row)
        bump("semantic_models", cls)
        inv["records"]["semantic_models"].append(
            {"id": str(row.id), "name": row.name, "key": row.key, "project_id": str(row.project_id), "class": cls}
        )
    inv["records"]["connectors"] = []
    for row in connectors:
        cls = classify_connector(row)
        bump("connectors", cls)
        inv["records"]["connectors"].append(
            {
                "id": str(row.id),
                "name": row.name,
                "key": row.key,
                "project_id": str(row.project_id),
                "connector_type": row.connector_type,
                "class": cls,
            }
        )
    inv["records"]["prompts"] = []
    for row in prompts:
        cls = classify_prompt(row)
        bump("prompts", cls)
        inv["records"]["prompts"].append(
            {
                "id": str(row.id),
                "name": row.name,
                "key": row.key,
                "scope": row.scope,
                "project_id": str(row.project_id) if row.project_id else None,
                "class": cls,
            }
        )
    inv["records"]["skills"] = []
    for row in skills:
        cls = classify_skill(row)
        bump("skills", cls)
        inv["records"]["skills"].append(
            {
                "id": str(row.id),
                "name": row.name,
                "key": row.key,
                "scope": row.scope,
                "project_id": str(row.project_id) if row.project_id else None,
                "class": cls,
            }
        )
    inv["records"]["projects"] = []
    for row in projects:
        cls = classify_project(row, preserved)
        bump("projects", cls)
        inv["records"]["projects"].append(
            {"id": str(row.id), "slug": row.slug, "name": row.name, "class": cls}
        )
    inv["classification_summary"] = {k: dict(v) for k, v in by_class.items()}
    return inv


def build_plan(inventory: dict[str, Any]) -> CleanupPlan:
    plan = CleanupPlan()
    plan.preserved.extend(
        [
            "Ask Data System Prompt (ask_data.system)",
            "RAG system prompt (rag.system)",
            "RAG insufficient evidence (rag.insufficient_evidence)",
            "Ask Data Analyst skill",
            "Document Q&A skill",
            f"Chat attachment libraries ({CHAT_ATTACHMENTS_LIBRARY_NAME})",
            "AI Model Registry (all providers/models/assignments)",
            "Alembic / migration metadata",
        ]
    )
    for rec in inventory["records"]["libraries"]:
        if rec["class"] == "C":
            plan.libraries.append(rec)
        elif rec["class"] == "D":
            plan.unknown.append({"kind": "library", **rec})
    for rec in inventory["records"]["semantic_models"]:
        if rec["class"] == "C":
            plan.semantic_models.append(rec)
        elif rec["class"] == "D":
            plan.unknown.append({"kind": "semantic_model", **rec})
    for rec in inventory["records"]["connectors"]:
        if rec["class"] == "C":
            plan.connectors.append(rec)
        elif rec["class"] == "D":
            plan.unknown.append({"kind": "connector", **rec})
    for rec in inventory["records"]["prompts"]:
        if rec["class"] == "C":
            plan.prompts.append(rec)
        elif rec["class"] == "D":
            plan.unknown.append({"kind": "prompt", **rec})
    for rec in inventory["records"]["skills"]:
        if rec["class"] == "C":
            plan.skills.append(rec)
        elif rec["class"] == "D":
            plan.unknown.append({"kind": "skill", **rec})
    for rec in inventory["records"]["projects"]:
        if rec["class"] == "C":
            plan.projects.append(rec)
        elif rec["class"] == "D":
            plan.unknown.append({"kind": "project", **rec})
    plan.conversations.append({"scope": "all", "class": "C", "note": "disposable chat/browser sessions"})
    return plan


def _delete_prompt(session: Session, prompt_id: uuid.UUID) -> None:
    row = session.get(PromptRow, prompt_id)
    if not row:
        return
    row.active_version_id = None
    session.flush()
    session.delete(row)


def _delete_skill(session: Session, skill_id: uuid.UUID) -> None:
    row = session.get(SkillRow, skill_id)
    if not row:
        return
    row.active_version_id = None
    session.flush()
    session.delete(row)


def _delete_semantic_runtime_for_model(session: Session, model_id: uuid.UUID) -> None:
    state = session.get(SemanticRuntimeStateRow, model_id)
    if state:
        state.active_deployment_id = None
        state.previous_deployment_id = None
        session.flush()
    deployments = list(
        session.execute(
            select(SemanticRuntimeDeploymentRow).where(SemanticRuntimeDeploymentRow.semantic_model_id == model_id)
        ).scalars().all()
    )
    for dep in deployments:
        dep.previous_deployment_id = None
    session.flush()
    for dep in deployments:
        session.delete(dep)
    if state:
        session.delete(state)
    session.flush()


def _delete_semantic_model(session: Session, model_id: uuid.UUID) -> None:
    row = session.get(SemanticModelRow, model_id)
    if not row:
        return
    _delete_semantic_runtime_for_model(session, model_id)
    row.active_version_id = None
    session.flush()
    session.delete(row)


def _purge_disposable_project_references(session: Session, project_id: uuid.UUID) -> None:
    """Remove test-project scoped AI assignments/registry rows (not workspace/global registry)."""
    session.execute(delete(ModelAssignmentRow).where(ModelAssignmentRow.project_id == project_id))
    session.execute(delete(ModelTestRunRow).where(ModelTestRunRow.project_id == project_id))
    session.execute(delete(AiModelRow).where(AiModelRow.project_id == project_id))
    session.execute(delete(AiProviderRow).where(AiProviderRow.project_id == project_id))
    session.execute(delete(UsageEventRow).where(UsageEventRow.project_id == project_id))


def _delete_project_conversations(session: Session, project_id: uuid.UUID) -> int:
    conv_ids = list(
        session.execute(select(ConversationRow.id).where(ConversationRow.project_id == project_id)).scalars().all()
    )
    if not conv_ids:
        return 0
    session.execute(delete(MessageRow).where(MessageRow.conversation_id.in_(conv_ids)))
    session.execute(delete(ConversationRow).where(ConversationRow.id.in_(conv_ids)))
    return len(conv_ids)


def _cleanup_project(
    session: Session,
    settings: Settings,
    project_id: uuid.UUID,
    *,
    delete_all_libraries: bool,
) -> dict[str, int]:
    stats = defaultdict(int)
    models = list(
        session.execute(select(SemanticModelRow).where(SemanticModelRow.project_id == project_id)).scalars().all()
    )
    for model in models:
        _delete_semantic_model(session, model.id)
        stats["semantic_models"] += 1
    session.flush()

    project = session.get(ProjectRow, project_id)
    if project and project.default_connector_id:
        project.default_connector_id = None
        session.flush()

    conn_svc = ConnectorRegistryService(session, settings=settings)
    connectors = list(
        session.execute(
            select(ConnectorRow).where(
                ConnectorRow.project_id == project_id,
            )
        ).scalars().all()
    )
    for conn in connectors:
        try:
            conn_svc.delete_connector(conn.id, workspace_id=conn.workspace_id, project_id=project_id)
            stats["connectors"] += 1
        except Exception:
            session.delete(conn)
            stats["connectors"] += 1
    session.flush()

    lib_svc = LibraryService(session, document_limit=settings.knowledge_max_documents_per_library)
    libraries = list(
        session.execute(select(LibraryRow).where(LibraryRow.project_id == project_id)).scalars().all()
    )
    for lib in libraries:
        if not delete_all_libraries and lib.name == CHAT_ATTACHMENTS_LIBRARY_NAME:
            continue
        lib_svc.delete_library(lib.id, settings=settings)
        stats["libraries"] += 1

    prompts = list(
        session.execute(select(PromptRow).where(PromptRow.project_id == project_id)).scalars().all()
    )
    for prompt in prompts:
        _delete_prompt(session, prompt.id)
        stats["prompts"] += 1
    session.flush()

    stats["conversations"] += _delete_project_conversations(session, project_id)
    session.commit()
    return dict(stats)


def apply_plan(session: Session, settings: Settings, plan: CleanupPlan) -> dict[str, Any]:
    preserved_slugs = preserved_project_slugs(settings)
    stats: dict[str, int] = defaultdict(int)

    # Global/workspace scoped cleanup (once).
    for rec in plan.prompts:
        if rec.get("scope") == "project":
            continue
        _delete_prompt(session, uuid.UUID(rec["id"]))
        stats["prompts"] += 1
    session.commit()

    for rec in plan.skills:
        _delete_skill(session, uuid.UUID(rec["id"]))
        stats["skills"] += 1
    session.commit()

    # Per disposable project: cascade project-owned metadata.
    disposable_ids = [uuid.UUID(p["id"]) for p in plan.projects]
    default_proj = session.execute(
        select(ProjectRow).where(ProjectRow.slug.in_(preserved_slugs))
    ).scalars().first()
    if default_proj:
        default_stats = _cleanup_project(
            session,
            settings,
            default_proj.id,
            delete_all_libraries=False,
        )
        for k, v in default_stats.items():
            stats[k] += v

    for pid in disposable_ids:
        if default_proj and pid == default_proj.id:
            continue
        proj_stats = _cleanup_project(session, settings, pid, delete_all_libraries=True)
        for k, v in proj_stats.items():
            stats[k] += v
        row = session.get(ProjectRow, pid)
        if row:
            usage_n = (
                session.execute(
                    select(func.count()).select_from(UsageEventRow).where(UsageEventRow.project_id == pid)
                ).scalar()
                or 0
            )
            _purge_disposable_project_references(session, pid)
            session.delete(row)
            stats["projects"] += 1
            stats["usage_events_project_scoped"] = int(stats.get("usage_events_project_scoped", 0)) + int(usage_n)
        session.commit()

    # Unknown global prompts classified D were skipped; unknown projects skipped.
    return dict(stats)


def print_summary(plan: CleanupPlan, *, dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"=== Demo cleanup ({mode}) ===")
    print(f"Knowledge:  {'would delete' if dry_run else 'deleted'} {len(plan.libraries)} test/demo libraries")
    print(f"Semantic:   {'would delete' if dry_run else 'deleted'} {len(plan.semantic_models)} test models")
    print(f"Prompts:    {'would delete' if dry_run else 'deleted'} {len(plan.prompts)} test prompts")
    print(f"Skills:     {'would delete' if dry_run else 'deleted'} {len(plan.skills)} test skills")
    print(f"Data Src:   {'would delete' if dry_run else 'deleted'} {len(plan.connectors)} connector records")
    print(f"Projects:   {'would delete' if dry_run else 'deleted'} {len(plan.projects)} disposable projects")
    print(f"Chat:       {'would delete' if dry_run else 'deleted'} all conversation history (scoped cleanup)")
    print("")
    print("Preserved:")
    for line in plan.preserved:
        print(f"  - {line}")
    if plan.unknown:
        print("")
        print(f"Unknown (not deleted): {len(plan.unknown)}")
        for item in plan.unknown[:15]:
            print(f"  - {item.get('kind')}: {item.get('name') or item.get('slug')} ({item.get('id')})")
        if len(plan.unknown) > 15:
            print(f"  ... and {len(plan.unknown) - 15} more")


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled demo environment cleanup (metadata only).")
    parser.add_argument("--dry-run", action="store_true", help="Report planned deletions (default).")
    parser.add_argument("--apply", action="store_true", help="Perform deletions.")
    parser.add_argument(
        "--confirm-local-db",
        action="store_true",
        help="Required with --apply to confirm local standalone DATABASE_URL.",
    )
    parser.add_argument(
        "--export-inventory",
        type=Path,
        help="Write full inventory JSON (no secrets) to this path.",
    )
    args = parser.parse_args()

    apply = bool(args.apply)
    dry_run = not apply
    if apply and not args.confirm_local_db:
        print("Refusing --apply without --confirm-local-db", file=sys.stderr)
        return 2

    settings = get_settings()
    assert_safe_environment(settings, apply=apply)
    factory = get_session_factory(settings.database_url)

    with factory() as session:
        inventory = collect_inventory(session, settings)
        plan = build_plan(inventory)

    if args.export_inventory:
        args.export_inventory.parent.mkdir(parents=True, exist_ok=True)
        args.export_inventory.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote inventory: {args.export_inventory}")

    print(f"Database target: {_db_identity(settings)}")
    print_summary(plan, dry_run=dry_run)

    if dry_run:
        return 0

    print("")
    print("Applying cleanup...")
    with factory() as session:
        stats = apply_plan(session, settings, plan)
    print("Apply stats:", json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
