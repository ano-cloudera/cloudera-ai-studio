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
    assert [t["type"] for t in tasks] == ["create_job", "run_job", "create_job", "run_job"]
    jobs = {t["entity_label"]: t for t in tasks if t["type"] == "create_job"}
    for job in jobs.values():
        assert (REPO / job["script"]).is_file(), job["script"]
    for run in (t for t in tasks if t["type"] == "run_job"):
        assert run["entity_label"] in jobs and run["wait_for"] is True
    assert list(jobs) == ["install-tools", "deploy-applications"]
    declared = METADATA["environment_variables"]
    manifest = yaml.safe_load((REPO / "deployment/cai/manifests/applications.yaml").read_text(encoding="utf-8"))
    forwarded = {n for app in manifest["applications"] for n in app.get("forward_env", [])}
    assert {"GEMINI_API_KEY", "TRINO_PASSWORD"} <= forwarded
    # The import form can store an edited value as "[object Object]" and Project Settings refuses empty rows,
    # so only variables with a real default are declared; keys and credentials are added after the import.
    assert all(str(spec.get("default", "")).strip() for spec in declared.values())
    assert not {n for n in declared if any(w in n for w in ("KEY", "PASSWORD", "SECRET", "TOKEN"))}


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


def test_vllm_setup_steps_appear_only_when_enabled(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_VLLM", raising=False)
    assert amp_setup.vllm_enabled() is False
    monkeypatch.setenv("ENABLE_VLLM", "true")
    monkeypatch.setattr(amp_setup, "VLLM_MODEL_ID", "org/some-model")
    assert amp_setup.vllm_enabled() is True
    assert [s.name for s in amp_setup.vllm_steps()] == ["vLLM virtualenv", "vLLM model weights"]


def test_job_scripts_do_not_raise_system_exit_on_success() -> None:
    # CAI runs job scripts through IPython, which marks a job failed when SystemExit(0) is raised.
    for name in ("setup.py", "deploy.py"):
        source = (REPO / "scripts" / "amp" / name).read_text()
        assert "raise SystemExit(main(" not in source, name
