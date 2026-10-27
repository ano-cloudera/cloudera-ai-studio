from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def dry_run(script: Path, env: dict[str, str]) -> dict:
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        env={**os.environ, "CAI_DRY_RUN": "1", **env},
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def load_entrypoint_without_file(script: Path) -> dict:
    namespace = {"__name__": "cai_interpreter_cell"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    return namespace


def test_impala_requirements_use_impyla_compatible_thrift_version() -> None:
    requirements = (ROOT / "backend" / "requirements-impala.txt").read_text(encoding="utf-8").splitlines()

    assert "impyla==0.22.0" in requirements
    assert "thrift==0.16.0" in requirements


def test_cai_entrypoints_keep_interpreter_alive_while_monitoring_child_processes() -> None:
    for relative_path in ("backend/app_cai_backend.py", "frontend/app_cai_frontend.py"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "os.execve" not in source
        assert "subprocess.Popen" in source
        assert ".poll()" in source


def test_frontend_portable_node_satisfies_vite_engine_requirement() -> None:
    namespace = load_entrypoint_without_file(ROOT / "frontend" / "app_cai_frontend.py")
    version = tuple(int(part) for part in namespace["NODE_VERSION"].split("."))

    assert version >= (20, 19, 0)


def test_backend_cai_entrypoint_uses_dynamic_port_and_local_proxy_bind() -> None:
    payload = dry_run(ROOT / "backend" / "app_cai_backend.py", {"CDSW_APP_PORT": "9876"})

    assert payload["cwd"].endswith("backend")
    assert payload["command"][-4:] == ["--host", "127.0.0.1", "--port", "9876"]


def test_backend_cai_entrypoint_resolves_checkout_without_file(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    namespace = load_entrypoint_without_file(ROOT / "backend" / "app_cai_backend.py")

    assert namespace["resolve_backend_dir"]() == ROOT / "backend"


def test_frontend_cai_entrypoint_uses_dynamic_port_and_backend_url() -> None:
    payload = dry_run(
        ROOT / "frontend" / "app_cai_frontend.py",
        {"CDSW_APP_PORT": "4321", "NEXT_PUBLIC_BACKEND_URL": "https://tempo-backend.example"},
    )

    assert payload["cwd"].endswith("frontend")
    assert payload["command"][-4:] == ["-H", "127.0.0.1", "-p", "4321"]
    assert payload["backend_url"] == "https://tempo-backend.example"


def test_frontend_cai_entrypoint_resolves_checkout_without_file(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    namespace = load_entrypoint_without_file(ROOT / "frontend" / "app_cai_frontend.py")

    assert namespace["resolve_frontend_dir"]() == ROOT / "frontend"


def test_frontend_cai_entrypoint_rejects_missing_backend_url() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "frontend" / "app_cai_frontend.py")],
        cwd=ROOT,
        env={**os.environ, "CAI_DRY_RUN": "1", "NEXT_PUBLIC_BACKEND_URL": ""},
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "NEXT_PUBLIC_BACKEND_URL is required" in result.stderr
