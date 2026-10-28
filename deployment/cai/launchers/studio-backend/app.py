from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    _REPO = Path(__file__).resolve().parents[4]
except NameError:  # CAI runs an Application script in a kernel, where __file__ is not defined
    _REPO = Path(os.environ.get("STUDIO_REPO_ROOT", "/home/cdsw/cloudera-ai-studio"))
_CAI = _REPO / "deployment" / "cai"
sys.path.insert(0, str(_CAI))

from common import http_ready, resolve_cai_port, run_supervised  # noqa: E402


def main() -> int:
    env = dict(os.environ)
    port = resolve_cai_port(env)
    py = env.get("PYTHON_EXECUTABLE", str(_REPO / ".venv/bin/python"))
    child = {
        **env,
        "BACKEND_HOST": "127.0.0.1",
        "BACKEND_PORT": str(port),
        "PORT": str(port),
        "CAI_DEPLOYMENT_PRESERVE_ENV": "1",
        "PYTHONPATH": str(_REPO / "backend"),
    }
    if env.get("CAI_ENV_FILE"):
        child["CAI_ENV_FILE"] = env["CAI_ENV_FILE"]
    return run_supervised(
        [py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
        env=child,
        cwd=str(_REPO / "backend"),
        readiness=lambda: http_ready(f"http://127.0.0.1:{port}/health"),
        startup_timeout=float(env.get("APP_STARTUP_TIMEOUT_MINUTES", "10")) * 60,
    )


if __name__ == "__main__":
    raise SystemExit(main())
