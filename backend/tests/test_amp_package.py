from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


amp_defaults = _load("amp_defaults", REPO / "deployment" / "cai" / "amp_defaults.py")
amp_setup = _load("amp_setup", REPO / "scripts" / "amp" / "setup.py")
METADATA = yaml.safe_load((REPO / ".project-metadata.yaml").read_text(encoding="utf-8"))


def test_urls_are_derived_from_the_workspace_domain() -> None:
    env = {"CDSW_DOMAIN": "ml-1.example.site"}
    backend = amp_defaults.with_amp_defaults(env, "backend")
    assert backend["QDRANT_URL"] == "https://anywhere-qdrant.ml-1.example.site:443"
    assert backend["CORS_ORIGINS"] == "https://anywhere-frontend.ml-1.example.site"
    frontend = amp_defaults.with_amp_defaults(env, "frontend")
    assert frontend["BACKEND_API_URL"] == "https://anywhere-backend.ml-1.example.site"


def test_explicit_values_and_a_missing_domain_win() -> None:
    env = {"CDSW_DOMAIN": "ml-1.example.site", "QDRANT_URL": "https://mine:443", "AMP_SUBDOMAIN_PREFIX": "demo"}
    assert amp_defaults.with_amp_defaults(env, "backend")["QDRANT_URL"] == "https://mine:443"
    assert amp_defaults.with_amp_defaults(env, "backend")["CORS_ORIGINS"] == "https://demo-frontend.ml-1.example.site"
    assert amp_defaults.with_amp_defaults({}, "backend") == {}


def test_metadata_matches_the_repository() -> None:
    assert METADATA["specification_version"] and METADATA["prototype_version"]
    tasks = METADATA["tasks"]
    assert tasks[0]["type"] == "run_session"
    for task in tasks:
        assert (REPO / task["script"]).is_file(), task["script"]
    apps = [t for t in tasks if t["type"] == "start_application"]
    assert [t["subdomain"] for t in apps] == ["anywhere-qdrant", "anywhere-backend", "anywhere-frontend"]
    assert all(t["static_subdomain"] is True for t in apps)
    prefix = METADATA["environment_variables"]["AMP_SUBDOMAIN_PREFIX"]["default"]
    assert all(t["subdomain"].startswith(prefix + "-") for t in apps)


def test_setup_steps_are_ordered_and_skippable() -> None:
    names = [s.name for s in amp_setup.build_steps()]
    assert names == [
        "Data folders",
        "Node.js",
        "Backend virtualenv",
        "Qdrant binary",
        "Qdrant web UI",
        "Embedding model",
        "Frontend dependencies",
    ]
    assert amp_setup.main(["--dry-run"]) == 0
