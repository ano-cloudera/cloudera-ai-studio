"""What this process is running, read once when it starts.

After a `git pull` the files on disk change but a process keeps the code it imported. The commit read at start is therefore the commit
of the code that answers: /version shows it, scripts/backend_version.py compares it with the disk, and the answer cache is keyed by it, so
an answer written by older code is never served by newer code.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _running_commit() -> str:
    try:
        done = subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[3]), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3, check=False)
        return done.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 - a checkout without git (a packaged copy) simply has no commit to show
        return "unknown"


RUNNING_COMMIT = _running_commit()
