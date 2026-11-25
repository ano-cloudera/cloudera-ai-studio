"""Serve an open model (Qwen by default) from this project on a GPU, as its own Application.

A separate job, so adding a model does not repeat the main setup (about 20 minutes). It does three things:
  1. applies the Qwen defaults below (a project variable of the same name always wins),
  2. builds the vLLM virtualenv and downloads the weights (scripts/amp/setup.py --vllm-only; finished steps are skipped),
  3. creates or updates the "Anywhere vLLM" Application (scripts/amp/deploy.py --only vllm) and waits until it runs,
  4. updates the Backend (it needs the vLLM key in its environment, so it restarts once),
  5. registers the model in Settings -> AI Models and gives it every capability that has no model yet (scripts/amp/register_llm.py).
     A model somebody already chose is never replaced.

Nothing here is needed when the project already uses a hosted model (Gemini, OpenAI, Anthropic) or an endpoint of its own.

Needs a GPU in the quota. The Application uses this project's runtime with GPU enabled (the Cloudera AI "Enable GPU" switch), so
no special runtime is needed; AMP_VLLM_RUNTIME_ID only names a different one. Usage: python scripts/amp/llm.py [--check]
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

# Qwen3.5-9B (Apache-2.0, about 18 GB in bf16) fits a 48 GB L40S with a large KV cache. Its model card asks for the qwen3_coder tool-call
# parser and the qwen3 reasoning parser, and the model thinks before it answers by default: thinking is switched off here because Ask
# Data needs the answer itself (a structured reply), not a think block. The card also asks for a recent vLLM ("main"); the venv
# pins VLLM_VERSION (0.29.0), so if the Application fails to load the model, set VLLM_VERSION to a newer release and run the job again.
# Not tested in this workspace. Any other model: set VLLM_MODEL_ID and the parser variables (Qwen3 non-Coder models use `hermes`).
DEFAULTS = {
    "ENABLE_VLLM": "true",
    "VLLM_MODEL_ID": "Qwen/Qwen3.5-9B",
    "GPU_PROFILE": "l40s",
    "VLLM_TOOL_CALL_PARSER": "qwen3_coder",
    "VLLM_REASONING_PARSER": "qwen3",
    "VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS": '{"enable_thinking": false}',
    "MAX_MODEL_LEN": "32768",
}
WEIGHTS_GB = 25  # free space wanted on the project filesystem before downloading


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
    if "/" not in env.get("VLLM_MODEL_ID", ""):
        problems.append(f"VLLM_MODEL_ID must be a Hugging Face id such as org/name, not '{env.get('VLLM_MODEL_ID', '')}'.")
    elif not (model_dir(env) / "config.json").is_file() and free_bytes < WEIGHTS_GB * 1024**3:
        problems.append(f"Only {free_bytes // 1024**3} GB are free on the project filesystem; the weights need about {WEIGHTS_GB} GB.")
    return problems, warnings


def backend_url(env: dict[str, str]) -> str:
    """The Backend URL with its secret path, derived exactly as the deploy job does."""
    sys.path.insert(0, str(ROOT / "scripts" / "amp"))
    import deploy  # noqa: PLC0415 - the deploy job owns the secret handling

    secured = deploy.with_studio_secrets(env)
    prefix = env.get("AMP_SUBDOMAIN_PREFIX", "").strip() or "anywhere"
    return f"https://{prefix}-backend.{env['CDSW_DOMAIN']}/{secured['STUDIO_API_TOKEN']}"


def vllm_url(env: dict[str, str]) -> str:
    prefix = env.get("AMP_SUBDOMAIN_PREFIX", "").strip() or "anywhere"
    return f"https://{prefix}-vllm.{env['CDSW_DOMAIN']}/v1"


def register(env: dict[str, str]) -> dict:
    sys.path.insert(0, str(ROOT / "scripts" / "amp"))
    import register_llm  # noqa: PLC0415

    name = env["VLLM_MODEL_ID"].rsplit("/", 1)[-1] + " (vLLM)"
    served = env.get("VLLM_MODEL") or "studio-llm"
    window = int(env["MAX_MODEL_LEN"]) if env.get("MAX_MODEL_LEN", "").isdigit() else None
    return register_llm.register(register_llm.make_call(backend_url(env)), base_url=vllm_url(env), name=name, served_name=served, context_window=window)


def run(script: str, args: list[str], env: dict[str, str]) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "amp" / script), *args], cwd=ROOT, env=env).returncode


def main(argv: list[str]) -> int:
    env = apply_defaults(dict(os.environ))
    problems, warnings = preflight(env, shutil.disk_usage(HOME).free if HOME.exists() else sys.maxsize)
    print(f"Model: {env['VLLM_MODEL_ID']}  GPU profile: {env['GPU_PROFILE']}  tool parser: {env['VLLM_TOOL_CALL_PARSER']}  vLLM: {env.get('VLLM_VERSION', 'venv default')}", flush=True)
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
    code = run("deploy.py", ["--only", "vllm"], env)
    if code:
        return code
    # The Backend reads the vLLM key from its environment (env://VLLM_API_KEY), so it is updated and restarted once.
    code = run("deploy.py", ["--only", "backend", "--skip-build"], env)
    if code:
        return code
    try:
        result = register(env)
    except Exception as exc:  # noqa: BLE001 - the Application runs; the registration can be done by hand
        print(f"The Application is running but the registration failed: {exc}", file=sys.stderr)
        print(f"Register it by hand in Settings -> AI Models: OpenAI-compatible, base URL {vllm_url(env)}, "
              f"secret env://VLLM_API_KEY, model name {env.get('VLLM_MODEL') or 'studio-llm'}.", file=sys.stderr)
        return 1
    print(f"Registered in AI Models. Given to: {', '.join(result['assigned']) or 'nothing (a model was already chosen for each)'}. "
          f"Connection test: {result['status']}.", flush=True)
    return 0


if __name__ == "__main__":
    # CAI runs job scripts through IPython, which reports even SystemExit(0) as a failed job: exit only on failure.
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
