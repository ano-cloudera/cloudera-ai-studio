"""Shared LLM env resolution (repo .env aliases). Mirrors backend-test conventions."""

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values


def gemini_model_from_env_files(*, backend_root: Path, repo_root: Path) -> str:
    for path in (backend_root / ".env", repo_root / ".env"):
        if not path.is_file():
            continue
        values = dotenv_values(path)
        for key in ("GEMINI_MODEL", "MODEL_GEMINI"):
            raw = str(values.get(key) or "").strip()
            if raw:
                return raw
    return ""
