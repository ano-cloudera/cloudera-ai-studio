"""Load and merge Ask Data runtime extension profiles (YAML)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


@lru_cache(maxsize=32)
def load_profile(name: str) -> dict[str, Any]:
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"runtime extension profile not found: {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def list_profile_names() -> list[str]:
    return sorted(p.stem for p in _PROFILES_DIR.glob("*.yaml"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _profile_matches_datasets(match: dict[str, Any] | None, datasets: dict[str, Any]) -> bool:
    if not match:
        return False
    needles = [str(s).casefold() for s in (match.get("source_substrings") or []) if s]
    if not needles:
        return False
    for dataset in datasets.values():
        source = str(dataset.get("source") or "").casefold()
        if any(n in source for n in needles):
            return True
    return False


def resolve_runtime_extensions(
    governance: dict[str, Any] | None,
    datasets: dict[str, Any],
) -> dict[str, Any] | None:
    """Governance `runtime_extensions` block, optional named profile, or auto-detect by match."""
    from app.semantic.runtime_extensions.engine import merge_glossary_into_runtime_extensions

    gov = governance if isinstance(governance, dict) else {}
    block = gov.get("runtime_extensions")
    if block is None:
        block = {}
    elif isinstance(block, str):
        block = {"profile": block.strip()}
    elif not isinstance(block, dict):
        block = {}

    merged: dict[str, Any] = {}
    profile_name = str(block.get("profile") or "").strip()
    if profile_name:
        merged = _deep_merge(load_profile(profile_name), block)
    elif block:
        merged = dict(block)
    else:
        for name in list_profile_names():
            candidate = load_profile(name)
            if _profile_matches_datasets(candidate.get("match"), datasets):
                merged = _deep_merge(candidate, block)
                break

    glossary_merge = merge_glossary_into_runtime_extensions(gov)
    if glossary_merge:
        merged = _deep_merge(glossary_merge, merged) if merged else glossary_merge
    return merged or None
