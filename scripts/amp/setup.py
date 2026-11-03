"""One-time setup for the Anywhere AI Studio AMP (runs as a Cloudera AI Session task).

Installs everything an Application cannot download: Node.js, the Backend venv, the Qdrant binary and UI,
the embedding model, the data folders and the Frontend dependencies. Every step is skipped when its result
already exists, so the script can be run again safely.

Usage: python scripts/amp/setup.py [--dry-run]
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    _HERE_ROOT = Path(__file__).resolve().parents[2]
except NameError:  # CAI runs job scripts in an IPython kernel, where __file__ is not defined; a job starts in the project root
    _HERE_ROOT = Path.cwd()
ROOT = Path(os.environ.get("STUDIO_REPO_ROOT") or _HERE_ROOT)
HOME = Path(os.environ.get("STUDIO_HOME", "/home/cdsw"))
NODE_HOME = Path(os.environ.get("NODE_HOME", str(HOME / "tools/node")))
VENV_PY = Path(os.environ.get("PYTHON_EXECUTABLE", str(HOME / ".venvs/studio-backend/bin/python")))
QDRANT_BIN = Path(os.environ.get("QDRANT_BINARY", str(HOME / "tools/qdrant/qdrant")))
QDRANT_UI = Path(os.environ.get("QDRANT_STATIC_DIR", str(HOME / "tools/qdrant/static")))
EMBEDDING = Path(os.environ.get("EMBEDDING_MODEL", str(HOME / "models/bge-m3")))
DATA = Path(os.environ.get("CAI_DATA_DIR", str(HOME / "anywhere-studio-data")))
VLLM_PY = HOME / ".venvs/studio-vllm/bin/python"
VLLM_MODEL_ID = os.environ.get("VLLM_MODEL_ID", "").strip()
VLLM_MODEL = Path(os.environ.get("MODEL_PATH") or (HOME / "models" / VLLM_MODEL_ID.rsplit("/", 1)[-1] if VLLM_MODEL_ID else HOME / "models/vllm"))


RERANKER = Path(os.environ.get("RERANKER_MODEL_PATH") or (HOME / "models/bge-reranker-v2-m3"))


def reranker_enabled() -> bool:
    return os.environ.get("ENABLE_RERANKER", "").strip().lower() in ("1", "true", "yes")


def vllm_enabled() -> bool:
    return os.environ.get("ENABLE_VLLM", "").strip().lower() in ("1", "true", "yes")


@dataclass
class Step:
    name: str
    done: bool
    command: list[str] | None = None
    action: object = None


def _path_with_node() -> str:
    return f"{NODE_HOME / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"


def make_data_dirs() -> None:
    for sub in ("metadata", "documents", "attachments", "exports", "logs", "var/semantic-runtime", "qdrant/storage"):
        (DATA / sub).mkdir(parents=True, exist_ok=True)


def build_steps() -> list[Step]:
    sh = ROOT / "scripts" / "cai"
    return [
        Step("Data folders", (DATA / "metadata").is_dir() and (DATA / "qdrant/storage").is_dir(), action=make_data_dirs),
        Step("Node.js", (NODE_HOME / "bin/node").is_file(), ["bash", str(sh / "prepare_node.sh"), str(NODE_HOME)]),
        Step("Backend virtualenv", VENV_PY.is_file(), ["bash", str(sh / "prepare_venvs.sh"), "backend"]),
        Step("Qdrant binary", QDRANT_BIN.is_file(), ["bash", str(sh / "prepare_qdrant_binary.sh"), str(QDRANT_BIN)]),
        Step("Qdrant web UI", (QDRANT_UI / "index.html").is_file(), ["bash", str(sh / "prepare_qdrant_ui.sh"), str(QDRANT_UI)]),
        Step("Embedding model", (EMBEDDING / "config.json").is_file(), ["bash", str(sh / "prepare_embedding_model.sh"), str(EMBEDDING)]),
        Step(
            "Frontend dependencies",
            (ROOT / "frontend/node_modules/.bin/next").is_file(),
            ["npm", "ci"],
        ),
    ]


def vllm_steps() -> list[Step]:
    sh = ROOT / "scripts" / "cai"
    steps = [Step("vLLM virtualenv", VLLM_PY.is_file(), ["bash", str(sh / "prepare_venvs.sh"), "vllm"])]
    if VLLM_MODEL_ID:
        steps.append(Step("vLLM model weights", (VLLM_MODEL / "config.json").is_file(), ["bash", str(sh / "prepare_vllm_model.sh"), str(VLLM_MODEL)]))
    else:
        print("ENABLE_VLLM is on but VLLM_MODEL_ID is empty: skipping the model download (set MODEL_PATH to weights already on disk).", flush=True)
    return steps


def reranker_steps() -> list[Step]:
    sh = ROOT / "scripts" / "cai"
    return [Step("Reranker model", (RERANKER / "config.json").is_file(), ["bash", str(sh / "prepare_reranker_model.sh"), str(RERANKER)])]


def run(step: Step) -> None:
    if step.action is not None:
        step.action()
        return
    env = {**os.environ, "PATH": _path_with_node(), "PIP_USER": "false"}
    cwd = ROOT / "frontend" if step.command and step.command[0] == "npm" else ROOT
    subprocess.run(step.command, cwd=cwd, env=env, check=True)


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    steps = build_steps() + (reranker_steps() if reranker_enabled() else []) + (vllm_steps() if vllm_enabled() else [])
    for number, step in enumerate(steps, 1):
        status = "skip (already done)" if step.done else ("would run" if dry else "run")
        print(f"[{number}/{len(steps)}] {step.name}: {status}", flush=True)
        if step.done or dry:
            continue
        try:
            run(step)
        except subprocess.CalledProcessError as exc:
            print(f"FAILED at step '{step.name}' (exit {exc.returncode}). Fix the error above and run the task again.", file=sys.stderr)
            return exc.returncode or 1
    print("Setup complete." if not dry else "Dry run complete.", flush=True)
    return 0


if __name__ == "__main__":
    # CAI runs job scripts through IPython, which reports even SystemExit(0) as a failed job: exit only on failure.
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
