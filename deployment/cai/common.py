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


def port_holders(port: int) -> list[tuple[int, str]]:
    """(pid, command line) of other processes listening on a TCP port. Linux /proc only; empty elsewhere."""
    inodes: set[str] = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) > 9 and fields[3] == "0A" and int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(fields[9])
    holders: list[tuple[int, str]] = []
    if not inodes:
        return holders
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                target = os.readlink(fd)
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
                    holders.append((int(entry.name), cmd))
                    break
        except OSError:
            continue
    return holders


def ensure_port_free(port: int, stale_marker: str, wait_seconds: float = 10.0) -> None:
    """Log who holds the port; stop leftovers of our own service (command line contains stale_marker)."""
    import sys

    holders = port_holders(port)
    for pid, cmd in holders:
        print(f"port {port} is held by pid {pid}: {cmd[:200]}", file=sys.stderr, flush=True)
        if stale_marker and stale_marker in cmd:
            print(f"stopping stale process {pid} left from a previous start", file=sys.stderr, flush=True)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    deadline = time.monotonic() + wait_seconds
    while port_holders(port) and time.monotonic() < deadline:
        time.sleep(0.5)
    remaining = port_holders(port)
    if remaining:
        raise RuntimeError(f"port {port} is still in use by {remaining}; stop that process or restart the Application")


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
