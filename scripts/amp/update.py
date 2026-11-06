"""Pull the latest code from GitHub and redeploy, as one Cloudera AI Job (no Session needed).

What it does, in order:
  1. `git pull --ff-only` in the project root. It never merges, resets or discards anything: if the pull cannot be a plain
     fast-forward (local edits in the way, or a diverged branch) it stops and says what to do.
  2. Nothing new: stops here (use --force-deploy to redeploy anyway).
  3. Backend requirements changed: installs them into the Backend virtualenv.
  4. Runs scripts/amp/deploy.py (builds the UI, updates and restarts the Applications, waits until they run).

Usage:
  python scripts/amp/update.py                 # pull, then deploy if something changed
  python scripts/amp/update.py --no-deploy     # only pull
  python scripts/amp/update.py --check         # read-only: fetch and say whether new commits are waiting
  python scripts/amp/update.py --force-deploy  # redeploy even when the pull brought nothing

The remote URL is never printed (it may carry a token); credentials in a URL are masked in any git message.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    _HERE_ROOT = Path(__file__).resolve().parents[2]
except NameError:  # CAI runs job scripts in an IPython kernel, where __file__ is not defined; a job starts in the project root
    _HERE_ROOT = Path.cwd()
ROOT = Path(os.environ.get("STUDIO_REPO_ROOT") or _HERE_ROOT)
HOME = Path(os.environ.get("STUDIO_HOME", "/home/cdsw"))
VENV_PY = Path(os.environ.get("PYTHON_EXECUTABLE", str(HOME / ".venvs/studio-backend/bin/python")))
GIT_TIMEOUT = 300
MAX_COMMITS_SHOWN = 15
_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@")


@dataclass
class Pull:
    ok: bool
    before: str = ""
    after: str = ""
    message: str = ""
    commits: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.ok and self.before != self.after


def mask(text: str) -> str:
    return _CREDENTIALS.sub(r"\1***@", text or "")


def git(root: Path, *args: str, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # a job cannot answer a password prompt
    return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True, timeout=timeout)


def _fail(message: str, process: subprocess.CompletedProcess | None = None) -> Pull:
    detail = mask(((process.stderr or process.stdout) if process else "").strip())
    return Pull(ok=False, message=message + (f"\n{detail}" if detail else ""))


def pull(root: Path) -> Pull:
    """A fast-forward pull of the current branch; the result says what came in. Never discards local work."""
    inside = git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        return _fail(f"{root} is not a git repository, so there is nothing to pull.", inside)
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if not branch:
        return _fail("The project is on a detached commit. In a Session run: git checkout main, then run this job again.")
    before = git(root, "rev-parse", "HEAD").stdout.strip()
    dirty = [line for line in git(root, "status", "--porcelain", "--untracked-files=no").stdout.splitlines() if line.strip()]
    result = git(root, "pull", "--ff-only")
    if result.returncode != 0:
        hint = ""
        if dirty:
            names = ", ".join(line[3:] for line in dirty[:5])
            hint = f"\nLocal edits to tracked files may be in the way ({names}). In a Session: git stash (keeps them) or git checkout -- <file> (drops them), then run this job again."
        else:
            hint = "\nThe branch has commits that are not on GitHub, or GitHub was rewritten. In a Session: git status and git log --oneline -3 show where it differs."
        return _fail("git pull --ff-only did not succeed." + hint, result)
    after = git(root, "rev-parse", "HEAD").stdout.strip()
    commits: list[str] = []
    files: list[str] = []
    if before != after:
        commits = git(root, "log", "--oneline", f"{before}..{after}").stdout.splitlines()
        files = git(root, "diff", "--name-only", before, after).stdout.splitlines()
    return Pull(ok=True, before=before, after=after, commits=commits, files=files, message=f"on {branch}")


def needs_backend_install(files: list[str]) -> bool:
    return any(re.fullmatch(r"backend/requirements[\w.-]*\.txt", name) for name in files)


def install_backend(root: Path) -> int:
    """The Backend virtualenv is built once by setup.py; new requirements are installed into it here."""
    if not VENV_PY.exists():
        print(f"Backend requirements changed, but {VENV_PY} does not exist. Run the Install tools and dependencies job first.", file=sys.stderr)
        return 1
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}  # CAI's addon site-packages must not hide the venv
    env["PIP_USER"] = "false"
    cmd = [str(VENV_PY), "-m", "pip", "install", "--no-user", "--retries", "10", "--timeout", "60", "-r", str(root / "backend" / "requirements.txt")]
    return subprocess.run(cmd, cwd=root, env=env).returncode


def run_deploy(root: Path) -> int:
    # A new process, so the deploy script that was just pulled is the one that runs.
    return subprocess.run([sys.executable, str(root / "scripts" / "amp" / "deploy.py")], cwd=root).returncode


def report(result: Pull) -> None:
    print(f"Pulled {result.message}: {result.before[:7]} -> {result.after[:7]}")
    for line in result.commits[:MAX_COMMITS_SHOWN]:
        print(f"  {line}")
    if len(result.commits) > MAX_COMMITS_SHOWN:
        print(f"  ... and {len(result.commits) - MAX_COMMITS_SHOWN} more commits")
    print(f"{len(result.commits)} commit(s), {len(result.files)} file(s) changed")


def check(root: Path) -> int:
    fetched = git(root, "fetch", "--quiet")
    if fetched.returncode != 0:
        print("git fetch did not succeed.\n" + mask((fetched.stderr or fetched.stdout).strip()), file=sys.stderr)
        return 1
    behind = git(root, "rev-list", "--count", "HEAD..@{upstream}")
    count = behind.stdout.strip() or "?"
    print(f"{count} new commit(s) on GitHub waiting to be pulled." if count not in ("0", "?") else "Up to date with GitHub." if count == "0" else "Could not compare with GitHub (no upstream branch).")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--no-deploy", action="store_true", help="only pull")
    parser.add_argument("--force-deploy", action="store_true", help="redeploy even when the pull brought nothing")
    parser.add_argument("--check", action="store_true", help="read-only: say whether new commits are waiting")
    args, _ = parser.parse_known_args(argv)  # the IPython kernel that runs CAI jobs adds '-f <kernel.json>' to argv
    if args.check:
        return check(ROOT)
    result = pull(ROOT)
    if not result.ok:
        print(result.message, file=sys.stderr)
        return 1
    if not result.changed:
        print(f"Already up to date ({result.after[:7]}). Nothing was redeployed; if the last deploy failed, run the Deploy applications job.")
        if args.no_deploy or not args.force_deploy:
            return 0
    else:
        report(result)
    if args.no_deploy:
        return 0
    if needs_backend_install(result.files):
        print("backend/requirements changed: installing into the Backend virtualenv.")
        code = install_backend(ROOT)
        if code:
            print("pip install failed, so nothing was redeployed. Fix the error above and run this job again.", file=sys.stderr)
            return code
    print("Redeploying the Applications.")
    return run_deploy(ROOT)


if __name__ == "__main__":
    # CAI runs job scripts through IPython, which reports even SystemExit(0) as a failed job: exit only on failure.
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
