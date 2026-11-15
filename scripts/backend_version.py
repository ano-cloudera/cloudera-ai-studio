"""Tell whether the running Backend has the code that is on disk: its commit (from /version) against `git rev-parse HEAD` here.

    python scripts/backend_version.py                  # in a Cloudera AI Session
    python scripts/backend_version.py --base-url https://<backend-app-url>/<secret>

A Backend keeps running the code it imported when it started, so after a `git pull` it needs a restart; this says when it does.
Prints no secret.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def verdict(running: str, on_disk: str) -> tuple[bool, str]:
    """(up to date, the sentence to show)."""
    if running in ("", "unknown"):
        return False, f"The Backend does not report its commit; on disk it is {on_disk}. Restart it to be sure."
    if on_disk.startswith(running) or running.startswith(on_disk):
        return True, f"Up to date: the Backend runs {running}, the same as on disk."
    return False, f"RESTART NEEDED: the Backend runs {running} but the code on disk is {on_disk} (a `git pull` came after it started)."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--base-url")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(HERE))
    import semantic_api  # noqa: PLC0415

    base_url = args.base_url or semantic_api.default_base_url()
    if not base_url:
        print("No Backend URL: run this in a Cloudera AI Session, or pass --base-url (with its secret path).", file=sys.stderr)
        return 2
    try:
        running = str(semantic_api.Api(base_url).call("GET", "/version").get("commit") or "")
    except RuntimeError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 1
    on_disk = subprocess.run(["git", "-C", str(HERE.parent), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    ok, sentence = verdict(running, on_disk)
    print(sentence)
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
