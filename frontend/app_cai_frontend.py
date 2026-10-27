"""Cloudera AI Application entrypoint for TEMPO Scan Frontend V2."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request


NODE_VERSION = "20.19.0"


def resolve_frontend_dir() -> Path:
    candidates: list[Path] = []
    project_dir = os.getenv("CDSW_PROJECT_DIR")
    if project_dir:
        base = Path(project_dir)
        candidates.extend([base, base / "frontend"])
        if base.is_dir():
            candidates.extend(path / "frontend" for path in base.iterdir() if path.is_dir())
    cwd = Path.cwd()
    candidates.extend([cwd, cwd / "frontend"])
    if cwd.is_dir():
        candidates.extend(path / "frontend" for path in cwd.iterdir() if path.is_dir())
    script_file = globals().get("__file__")
    if script_file:
        candidates.append(Path(script_file).resolve().parent)
    for candidate in candidates:
        if (candidate / "package.json").is_file() and (candidate / "package-lock.json").is_file() and (candidate / "src").is_dir():
            return candidate.resolve()
    raise RuntimeError("Could not locate frontend checkout")


def ensure_node(frontend_dir: Path) -> Path:
    system_node = shutil.which("node")
    system_npm = shutil.which("npm")
    if system_node and system_npm:
        return Path(system_node).parent
    machine = platform.machine().casefold()
    arch = "x64" if machine in {"x86_64", "amd64"} else "arm64" if machine in {"aarch64", "arm64"} else None
    if arch is None:
        raise RuntimeError(f"Unsupported CPU architecture: {machine}")
    dist = f"node-v{NODE_VERSION}-linux-{arch}"
    install_root = frontend_dir / ".node-runtime"
    bin_dir = install_root / dist / "bin"
    if (bin_dir / "node").is_file():
        return bin_dir
    install_root.mkdir(parents=True, exist_ok=True)
    archive = install_root / f"{dist}.tar.xz"
    urllib.request.urlretrieve(f"https://nodejs.org/dist/v{NODE_VERSION}/{archive.name}", archive)
    with tarfile.open(archive, "r:xz") as bundle:
        bundle.extractall(install_root)
    archive.unlink()
    return bin_dir


def main() -> None:
    frontend_dir = resolve_frontend_dir()
    port = os.getenv("CDSW_APP_PORT") or os.getenv("PORT") or "3000"
    backend_url = os.getenv("NEXT_PUBLIC_BACKEND_URL") or os.getenv("NEXT_PUBLIC_BACKEND_API_URL") or ""
    if not backend_url:
        raise RuntimeError("NEXT_PUBLIC_BACKEND_URL is required")
    if not backend_url.startswith(("http://", "https://")):
        raise RuntimeError("NEXT_PUBLIC_BACKEND_URL must start with http:// or https://")
    os.environ["BACKEND_API_URL"] = backend_url.rstrip("/")
    if os.getenv("CAI_DRY_RUN") == "1":
        command = ["node", "next", "start", "-H", "127.0.0.1", "-p", str(port)]
        print(json.dumps({"cwd": str(frontend_dir), "command": command, "backend_url": backend_url}))
        return

    bin_dir = ensure_node(frontend_dir)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    npm = bin_dir / "npm"
    node = bin_dir / "node"
    next_cli = frontend_dir / "node_modules" / "next" / "dist" / "bin" / "next"
    marker = frontend_dir / "node_modules" / ".tempo-v2-lock-installed"
    lock = frontend_dir / "package-lock.json"
    if not marker.exists() or marker.stat().st_mtime < lock.stat().st_mtime:
        subprocess.check_call([str(npm), "ci"], cwd=frontend_dir, env=env)
        marker.write_text("ok\n", encoding="utf-8")
    subprocess.check_call([str(node), str(next_cli), "build"], cwd=frontend_dir, env=env)
    command = [str(node), str(next_cli), "start", "-H", "127.0.0.1", "-p", str(port)]
    print(f"[frontend] starting on 127.0.0.1:{port}; backend={backend_url}", flush=True)
    process = subprocess.Popen(command, cwd=frontend_dir, env=env)
    print(f"[frontend] PID: {process.pid}", flush=True)
    try:
        while True:
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeError(f"Frontend V2 exited with code {return_code}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("[frontend] application interrupted", flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        print("[frontend] application stopped", flush=True)


if __name__ == "__main__":
    main()
