"""Shared helpers for Cloudera AI Application launchers (adapted from BNI CAI training kit)."""
from __future__ import annotations

import os
import signal
import subprocess
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path


def launcher_roots(app_file: str | Path) -> tuple[Path, Path]:
    """(deployment/cai dir, repo root) for deployment/cai/launchers/<app>/app.py."""
    path = Path(app_file).resolve()
    return path.parents[2], path.parents[4]


def repo_root_from(app_file: str | Path) -> Path:
    return launcher_roots(app_file)[1]


def resolve_cai_port(env: Mapping[str, str]) -> int:
    mode = env.get("CAI_PORT_MODE", "app").strip().lower()
    key = "CDSW_READONLY_PORT" if mode == "readonly" else "CDSW_APP_PORT"
    value = env.get(key, "")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"CAI Application port {key} is missing or invalid") from exc
    if port < 1 or port > 65535:
        raise ValueError(f"CAI Application port {key} is outside 1-65535")
    return port


def build_child_env(env: Mapping[str, str]) -> dict[str, str]:
    result = dict(os.environ)
    result.update(env)
    return result


def http_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return 200 <= response.status < 500
    except OSError:
        return False


def run_supervised(
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    readiness: Callable[[], bool] | None = None,
    startup_timeout: float = 300.0,
    poll_interval: float = 1.0,
) -> int:
    if isinstance(command, (str, bytes)) or not command:
        raise TypeError("command must be a non-empty argument list")
    process = subprocess.Popen(
        list(command),
        env=build_child_env(env or {}),
        cwd=str(cwd) if cwd else None,
        shell=False,
    )
    previous_handlers: dict[int, object] = {}

    def forward(signum: int, _frame: object) -> None:
        if process.poll() is None:
            process.send_signal(signum)

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, forward)

    try:
        if readiness is not None:
            deadline = time.monotonic() + startup_timeout
            while not readiness():
                code = process.poll()
                if code is not None:
                    return code
                if time.monotonic() >= deadline:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    raise TimeoutError("service readiness check timed out")
                time.sleep(poll_interval)
        return process.wait()
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
