"""Serve an open model (Qwen by default) from this project on a GPU, as its own Application.

A separate job, so adding a model does not repeat the main setup (about 20 minutes). It does three things:
  1. applies the Qwen defaults below (a project variable of the same name always wins),
  2. builds the vLLM virtualenv and downloads the weights (scripts/amp/setup.py --vllm-only; finished steps are skipped),
  3. creates or updates the "Anywhere vLLM" Application (scripts/amp/deploy.py --only vllm) and waits until it runs.

Then register it once in Settings -> AI Models as an OpenAI-compatible provider: base URL https://<vllm application URL>/v1,
model name studio-llm (the deploy log prints both).

Needs a GPU runtime (AMP_VLLM_RUNTIME_ID) and a GPU in the quota. Usage: python scripts/amp/llm.py [--check]
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    ROOT = Path(__file__).resolve().parents[2]
except NameError:  # CAI runs job scripts in an IPython kernel, where __file__ is not defined; a job starts in the project root
    ROOT = Path.cwd()
HOME = Path(os.environ.get("STUDIO_HOME", "/home/cdsw"))

# A 48 GB L40S holds this model in FP8 (about 31 GB of weights) and leaves room for the KV cache; only 3B parameters are active
# per token, so answers are fast. Not tested in this workspace: change the id with VLLM_MODEL_ID (a smaller Qwen3 such as
# Qwen/Qwen3-14B also fits). `hermes` is vLLM's tool-call parser for Qwen3; Qwen3-Coder models use `qwen3_coder`.
DEFAULTS = {
    "ENABLE_VLLM": "true",
    "VLLM_MODEL_ID": "Qwen/Qwen3-30B-A3B-Instruct-2507-FP8",
    "GPU_PROFILE": "l40s",
    "VLLM_TOOL_CALL_PARSER": "hermes",
}
WEIGHTS_GB = 40  # free space wanted on the project filesystem before downloading


def apply_defaults(env: dict[str, str]) -> dict[str, str]:
    """The environment with the Qwen defaults added where the project did not set a value."""
    out = dict(env)
    for name, value in DEFAULTS.items():
        if not out.get(name, "").strip():
            out[name] = value
    return out


def model_dir(env: dict[str, str]) -> Path:
    return Path(env.get("MODEL_PATH") or HOME / "models" / env["VLLM_MODEL_ID"].rsplit("/", 1)[-1])


def preflight(env: dict[str, str], free_bytes: int) -> tuple[list[str], list[str]]:
    """(problems that stop the job, warnings). Nothing is downloaded or created here."""
    problems, warnings = [], []
    if not env.get("AMP_VLLM_RUNTIME_ID", "").strip():
        warnings.append("AMP_VLLM_RUNTIME_ID is not set: the standard runtime cannot use the GPU. Set it to a GPU-enabled runtime "
                        "if the Application starts without CUDA (ask the workspace admin which runtime to use).")
    if "/" not in env.get("VLLM_MODEL_ID", ""):
        problems.append(f"VLLM_MODEL_ID must be a Hugging Face id such as org/name, not '{env.get('VLLM_MODEL_ID', '')}'.")
    elif not (model_dir(env) / "config.json").is_file() and free_bytes < WEIGHTS_GB * 1024**3:
        problems.append(f"Only {free_bytes // 1024**3} GB are free on the project filesystem; the weights need about {WEIGHTS_GB} GB.")
    return problems, warnings


def run(script: str, args: list[str], env: dict[str, str]) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "amp" / script), *args], cwd=ROOT, env=env).returncode


def main(argv: list[str]) -> int:
    env = apply_defaults(dict(os.environ))
    problems, warnings = preflight(env, shutil.disk_usage(HOME).free if HOME.exists() else sys.maxsize)
    print(f"Model: {env['VLLM_MODEL_ID']}  GPU profile: {env['GPU_PROFILE']}  tool parser: {env['VLLM_TOOL_CALL_PARSER']}", flush=True)
    for line in warnings:
        print(f"Warning: {line}", flush=True)
    for line in problems:
        print(f"Stopped: {line}", file=sys.stderr)
    if problems:
        return 1
    if "--check" in argv:
        print("Checks passed.", flush=True)
        return 0
    code = run("setup.py", ["--vllm-only"], env)
    if code:
        print("The vLLM environment or the weights could not be prepared; fix the error above and run this job again.", file=sys.stderr)
        return code
    return run("deploy.py", ["--only", "vllm"], env)


if __name__ == "__main__":
    # CAI runs job scripts through IPython, which reports even SystemExit(0) as a failed job: exit only on failure.
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
