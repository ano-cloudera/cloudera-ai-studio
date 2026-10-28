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

from common import http_ready, resolve_cai_port, log_cai_endpoint, run_supervised  # noqa: E402


def main() -> int:
    env = dict(os.environ)
    log_cai_endpoint()
    node_home = env.get("NODE_HOME", "").strip()
    if node_home:  # CAI runtimes ship without Node; npm's shebang needs `node` on PATH
        env["PATH"] = f"{node_home}/bin{os.pathsep}{env.get('PATH', '')}"
        env.setdefault("NPM_EXECUTABLE", f"{node_home}/bin/npm")
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
    # Call Next directly: `npm run start` hardcodes -H 0.0.0.0, which collides with CAI's pod-IP listener on the
    # Application port. CAI expects Applications on loopback.
    return run_supervised(
        [str(fe / "node_modules" / ".bin" / "next"), "start", "-H", "127.0.0.1", "-p", str(port)],
        env=child,
        cwd=fe,
        readiness=lambda: http_ready(f"http://127.0.0.1:{port}/"),
        startup_timeout=float(env.get("APP_STARTUP_TIMEOUT_MINUTES", "15")) * 60,
    )


if __name__ == "__main__":
    raise SystemExit(main())
