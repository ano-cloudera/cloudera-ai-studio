from __future__ import annotations

import os
import sys
from pathlib import Path

_CAI, _REPO = Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_CAI))

from common import http_ready, resolve_cai_port, run_supervised  # noqa: E402


def main() -> int:
    env = dict(os.environ)
    port = resolve_cai_port(env)
    npm = env.get("NPM_EXECUTABLE", "npm")
    fe = _REPO / "frontend"
    if not (fe / ".next").is_dir() and env.get("CAI_SKIP_FRONTEND_BUILD", "") != "1":
        run_supervised([npm, "run", "build"], cwd=fe, env=env)
    child = {
        **env,
        "PORT": str(port),
        "HOST": "127.0.0.1",
        "BACKEND_API_URL": env.get("BACKEND_API_URL", ""),
    }
    return run_supervised(
        [npm, "run", "start"],
        env=child,
        cwd=fe,
        readiness=lambda: http_ready(f"http://127.0.0.1:{port}/"),
        startup_timeout=float(env.get("APP_STARTUP_TIMEOUT_MINUTES", "15")) * 60,
    )


if __name__ == "__main__":
    raise SystemExit(main())
