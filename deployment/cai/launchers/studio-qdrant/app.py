from __future__ import annotations

import os
import sys
import threading
from collections.abc import Mapping
from pathlib import Path

try:
    _REPO = Path(__file__).resolve().parents[4]
except NameError:  # CAI runs an Application script in a kernel, where __file__ is not defined
    _REPO = Path(os.environ.get("STUDIO_REPO_ROOT", "/home/cdsw/cloudera-ai-studio"))
_CAI = _REPO / "deployment" / "cai"
_LAUNCHER = _CAI / "launchers" / "studio-qdrant"
sys.path.insert(0, str(_CAI))

from common import http_ready, resolve_cai_port, run_supervised  # noqa: E402


def build_command(env: Mapping[str, str]) -> list[str]:
    binary = env.get("QDRANT_BINARY", "")
    if not binary:
        raise ValueError("QDRANT_BINARY is required")
    return [binary]


def check_binary(env: Mapping[str, str]) -> Path:
    path = Path(env.get("QDRANT_BINARY", ""))
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(
            f"Qdrant binary not found at {path}. Run: bash scripts/cai/prepare_qdrant_binary.sh"
        )
    return path


def build_environment(env: Mapping[str, str]) -> dict[str, str]:
    port = resolve_cai_port(env)
    storage = Path(env.get("QDRANT_STORAGE_PATH", "/tmp/cai-qdrant"))
    storage.mkdir(parents=True, exist_ok=True)
    child = dict(env)
    child.update(
        {
            "QDRANT__SERVICE__HOST": "127.0.0.1",
            "QDRANT__SERVICE__HTTP_PORT": str(port),
            "QDRANT__SERVICE__GRPC_PORT": "0",
            "QDRANT__STORAGE__STORAGE_PATH": str(storage),
        }
    )
    if env.get("QDRANT_API_KEY"):
        child["QDRANT__SERVICE__API_KEY"] = env["QDRANT_API_KEY"]
    return child


def _start_dashboard_if_configured(env: Mapping[str, str], qdrant_port: int) -> None:
    readonly = (env.get("CDSW_READONLY_PORT") or "").strip()
    if not readonly:
        return
    try:
        ui_port = int(readonly)
    except ValueError:
        return

    def _run() -> None:
        import subprocess

        subprocess.run(
            [
                sys.executable,
                str(_LAUNCHER / "dashboard.py"),
                "--qdrant-url",
                f"http://127.0.0.1:{qdrant_port}",
                "--port",
                str(ui_port),
            ],
            check=False,
        )

    threading.Thread(target=_run, daemon=True).start()


def main() -> int:
    env = dict(os.environ)
    build_command(env)
    check_binary(env)
    port = resolve_cai_port(env)
    _start_dashboard_if_configured(env, port)
    return run_supervised(
        build_command(env),
        env=build_environment(env),
        readiness=lambda: http_ready(f"http://127.0.0.1:{port}/readyz"),
        startup_timeout=float(env.get("APP_STARTUP_TIMEOUT_MINUTES", "5")) * 60,
    )


if __name__ == "__main__":
    raise SystemExit(main())
