#!/usr/bin/env python3
"""Accelerator configuration doctor (no secrets printed)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings
from app.llm.registry import ProviderRegistry
from app.platform.readiness import build_readiness_report


def _mark(status: str) -> str:
    if status in {"ready", "ok", "not_required", "optional"}:
        return "✓"
    if status in {"not_configured", "skipped", "mock"}:
        return "○"
    return "✗"


def main() -> int:
    settings = get_settings()
    report = build_readiness_report(settings, provider_registry=ProviderRegistry(settings))
    print(f"Cloudera AI Accelerator doctor ({report['components']['accelerator_version']})")
    print(f"Profile: deployment={settings.deployment_profile} features={settings.feature_profile}")
    print("")
    print("Platform")
    for key in ("postgres", "document_storage", "semantic_runtime_storage", "llm", "legacy_datasource"):
        comp = report["components"].get(key)
        if isinstance(comp, dict):
            print(f"  {_mark(str(comp.get('status', '')))} {key}: {comp.get('status')}")
        else:
            print(f"  {_mark(str(comp))} {key}: {comp}")
    print("")
    print("RAG (optional unless FEATURE_PROFILE requires RAG)")
    for key in ("qdrant", "embeddings", "reranker"):
        comp = report["components"].get(key)
        if isinstance(comp, dict):
            print(f"  {_mark(str(comp.get('status', '')))} {key}: {comp.get('status')}")
        else:
            print(f"  {_mark(str(comp))} {key}: {comp}")
    print("")
    if report.get("feature_gaps"):
        print("Feature gaps:", ", ".join(report["feature_gaps"]))
    print(f"Core ready: {report.get('core_ready')}")
    return 0 if report.get("core_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
