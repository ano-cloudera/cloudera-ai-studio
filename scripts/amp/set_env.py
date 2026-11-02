"""Repair project environment variables through the CAI API (run in a Session terminal).

Some Cloudera AI versions save values typed in the AMP form or in Project Settings as "[object Object]". This script asks for
the affected variables again and stores them as plain text through the API. Secrets are read without echo and never printed.

Usage: python scripts/amp/set_env.py [NAME ...]    (no names: every variable that is not plain text)
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy  # noqa: E402

MANIFEST = Path(__file__).resolve().parents[2] / ".project-metadata.yaml"
SECRET_WORDS = ("KEY", "PASSWORD", "SECRET", "TOKEN")


def defaults(path: Path = MANIFEST) -> dict[str, str]:
    declared = (yaml.safe_load(path.read_text(encoding="utf-8")).get("environment_variables") or {})
    return {name: str(spec.get("default", "")) for name, spec in declared.items()}


def repair(client, names: list[str], ask, known_defaults: dict[str, str]) -> list[str]:
    """Ask for each name (the given ones, or every non-text variable) and store all variables as plain text."""
    current = client.project_variables()
    targets = names or sorted(n for n, v in current.items() if not isinstance(v, str))
    merged = {n: v for n, v in current.items() if isinstance(v, str)}
    for name in targets:
        merged[name] = ask(name, known_defaults.get(name, ""))
    client.set_project_variables(merged)
    return targets


def ask_interactively(name: str, default: str) -> str:
    secret = any(word in name for word in SECRET_WORDS)
    label = f"{name}" + (f" [{default}]" if default and not secret else "") + ": "
    value = (getpass.getpass(label) if secret else input(label)).strip()
    return value or default


def main(argv: list[str]) -> int:
    env = os.environ
    missing = [n for n in ("CDSW_DOMAIN", "CDSW_PROJECT_ID") if not env.get(n)]
    token = env.get("CDSW_APIV2_KEY") or env.get("CML_API_KEY")
    if missing or not token:
        print("Run this inside a Cloudera AI Session (CDSW_DOMAIN, CDSW_PROJECT_ID and CDSW_APIV2_KEY are needed).", file=sys.stderr)
        return 2
    client = deploy.Cml(env["CDSW_DOMAIN"], env["CDSW_PROJECT_ID"], token)
    try:
        names = [a for a in argv if not a.startswith("-")]
        if not names and not client.non_string_project_variables():
            print("No broken variables found. Pass names to set them anyway: python scripts/amp/set_env.py NAME ...")
            return 0
        done = repair(client, names, ask_interactively, defaults())
    except deploy.ApiError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Stored as plain text: {', '.join(done)}. Check Project Settings -> Advanced, then run the Deploy applications job.")
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
