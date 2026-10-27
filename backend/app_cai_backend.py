"""Cloudera AI Application entrypoint for TEMPO Scan Backend V2.

This keeps the proven V1 pattern: resolve the checkout defensively, install
dependencies into an application-local virtualenv, bind to CAI's dynamic port
on 127.0.0.1, and let the CAI reverse proxy provide external HTTPS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time


def resolve_backend_dir() -> Path:
    candidates: list[Path] = []
    project_dir = os.getenv("CDSW_PROJECT_DIR")
    if project_dir:
        base = Path(project_dir)
        candidates.extend([base, base / "backend"])
        if base.is_dir():
            candidates.extend(path / "backend" for path in base.iterdir() if path.is_dir())
    cwd = Path.cwd()
    candidates.extend([cwd, cwd / "backend"])
    if cwd.is_dir():
        candidates.extend(path / "backend" for path in cwd.iterdir() if path.is_dir())
    script_file = globals().get("__file__")
    if script_file:
        candidates.append(Path(script_file).resolve().parent)
    for candidate in candidates:
        if (candidate / "app" / "main.py").is_file() and (candidate / "requirements.txt").is_file():
            return candidate.resolve()
    raise RuntimeError("Could not locate backend checkout")


def ensure_venv(backend_dir: Path) -> Path:
    venv_dir = backend_dir / ".venv-cai"
    python = venv_dir / "bin" / "python"
    marker = venv_dir / ".requirements-installed"
    requirements = [backend_dir / "requirements.txt", backend_dir / "requirements-impala.txt"]
    if not python.is_file():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    newest = max(path.stat().st_mtime for path in requirements)
    if not marker.exists() or marker.stat().st_mtime < newest:
        env = os.environ.copy()
        env.pop("PIP_USER", None)
        env.pop("PYTHONUSERBASE", None)
        for path in requirements:
            subprocess.check_call([str(python), "-m", "pip", "--isolated", "install", "--no-user", "-r", str(path)], env=env)
        marker.write_text("ok\n", encoding="utf-8")
    return python


def main() -> None:
    backend_dir = resolve_backend_dir()
    port = os.getenv("CDSW_APP_PORT") or os.getenv("PORT") or "8000"
    dry_run = os.getenv("CAI_DRY_RUN") == "1"
    python = Path(sys.executable) if dry_run else ensure_venv(backend_dir)
    command = [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    if dry_run:
        print(json.dumps({"cwd": str(backend_dir), "command": command}))
        return
    os.environ["PYTHONPATH"] = str(backend_dir) + os.pathsep + os.environ.get("PYTHONPATH", "")
    print(f"[backend] starting on 127.0.0.1:{port}", flush=True)
    process = subprocess.Popen(command, cwd=backend_dir, env=os.environ.copy())
    print(f"[backend] PID: {process.pid}", flush=True)
    try:
        while True:
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeError(f"Backend V2 exited with code {return_code}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("[backend] application interrupted", flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        print("[backend] application stopped", flush=True)


if __name__ == "__main__":
    main()
