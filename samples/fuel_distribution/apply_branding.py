#!/usr/bin/env python3
"""Show the customer's logo in the sidebar and on the empty chat for the demo, and take it away again (temporary, not part of the AMP).

    python3 samples/fuel_distribution/apply_branding.py            # copy the logo into the Frontend's public folder, print what to set
    python3 samples/fuel_distribution/apply_branding.py --remove   # delete the copy, print what to unset

The AMP's own logo is never touched: the Frontend reads the logo path from NEXT_PUBLIC_PRODUCT_LOGO (and NEXT_PUBLIC_EMPTY_STATE_LOGO
for the empty chat), so the demo is switched on by setting those two variables and off by removing them. The copy goes to
frontend/public/branding/demo/, which is ignored by git. Set the variables where the Frontend's other settings are, then restart the
Frontend (a file added to public/ after a build is only served after the Frontend is started again).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGO = HERE / "branding" / "pertamina-logo.png"
DEFAULT_PUBLIC = ROOT / "frontend" / "public"
URL = "/branding/demo/pertamina-logo.png"
VARIABLES = ("NEXT_PUBLIC_PRODUCT_LOGO", "NEXT_PUBLIC_EMPTY_STATE_LOGO")


def apply(public_dir: Path = DEFAULT_PUBLIC, *, remove: bool = False) -> list[str]:
    """Copy (or delete) the logo under `public_dir` and return the lines to show the person running it."""
    target = public_dir / "branding" / "demo" / LOGO.name
    if remove:
        if target.exists():
            target.unlink()
        for folder in (target.parent,):
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        return ["Removed the demo logo.", "Unset, then restart the Frontend:", *[f"  {name}" for name in VARIABLES]]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(LOGO, target)
    return [f"Copied the demo logo to {target}", "Set, then restart the Frontend:", *[f"  {name}={URL}" for name in VARIABLES]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--remove", action="store_true", help="delete the copy and say what to unset")
    parser.add_argument("--public-dir", type=Path, default=DEFAULT_PUBLIC, help="the Frontend's public folder")
    args = parser.parse_args(argv)
    if not args.remove and not LOGO.exists():
        print(f"No logo at {LOGO}", file=sys.stderr)
        return 2
    print("\n".join(apply(args.public_dir, remove=args.remove)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
