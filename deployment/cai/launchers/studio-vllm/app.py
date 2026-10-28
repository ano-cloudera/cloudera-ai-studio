from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

try:
    _REPO = Path(__file__).resolve().parents[4]
except NameError:  # CAI runs an Application script in a kernel, where __file__ is not defined
    _REPO = Path(os.environ.get("STUDIO_REPO_ROOT", "/home/cdsw/cloudera-ai-studio"))
_CAI = _REPO / "deployment" / "cai"
sys.path.insert(0, str(_CAI))

from common import http_ready, resolve_cai_port, run_supervised  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_SERVED_MODEL = "studio-llm"
GPU_PROFILES = {
    "l40s": {"gpu_memory_utilization": "0.82", "max_model_len": "8192", "max_num_seqs": "16"},
    "h200": {"gpu_memory_utilization": "0.75", "max_model_len": "8192", "max_num_seqs": "32"},
}


def validate_model_path(raw: str) -> Path:
    path = Path(raw.strip())
    if not path.is_dir():
        raise ValueError(f"MODEL_PATH must be an existing model directory: {path}")
    if not (path / "config.json").is_file() and not any(path.glob("*.safetensors")):
        raise ValueError(f"MODEL_PATH has no config.json or .safetensors files: {path}")
    return path


def cuda_toolkit_available(env: Mapping[str, str]) -> bool:
    """True when nvcc is on PATH, in CUDA_HOME or in /usr/local/cuda. Nothing is installed."""
    if shutil.which("nvcc", path=env.get("PATH", os.environ.get("PATH", ""))):
        return True
    return any(root and (Path(root) / "bin" / "nvcc").is_file() for root in (env.get("CUDA_HOME", ""), "/usr/local/cuda"))


def runtime_environment(env: Mapping[str, str]) -> dict[str, str]:
    """Child env extras: no model download; FlashInfer sampler off without nvcc (explicit value wins)."""
    # Empty PYTHONPATH keeps CAI addon site-packages out of the venv interpreter.
    extra = {"HF_HUB_OFFLINE": env.get("HF_HUB_OFFLINE", "1"), "PYTHONPATH": ""}
    if "VLLM_USE_FLASHINFER_SAMPLER" not in env and not cuda_toolkit_available(env):
        extra["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
    return extra


def resolve_port(env: Mapping[str, str]) -> int:
    if not env.get("CDSW_APP_PORT", "").strip():
        return int(env.get("VLLM_FALLBACK_PORT", "8101"))
    return resolve_cai_port({"CDSW_APP_PORT": env["CDSW_APP_PORT"]})


def build_command(env: Mapping[str, str]) -> list[str]:
    model = validate_model_path(env.get("MODEL_PATH", ""))
    profile_name = env.get("GPU_PROFILE", "h200").lower()
    if profile_name not in GPU_PROFILES:
        raise ValueError(f"GPU_PROFILE must be one of {sorted(GPU_PROFILES)}")
    profile = GPU_PROFILES[profile_name]
    port = resolve_port(env)
    command = [
        env.get("PYTHON_EXECUTABLE", "python"),
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        str(model),
        "--served-model-name",
        env.get("VLLM_MODEL") or env.get("SERVED_MODEL_NAME") or DEFAULT_SERVED_MODEL,
        "--host",
        env.get("VLLM_HOST", DEFAULT_HOST),
        "--port",
        str(port),
        "--tensor-parallel-size",
        env.get("TENSOR_PARALLEL_SIZE", "1"),
        "--dtype",
        env.get("VLLM_DTYPE", "bfloat16"),
        "--max-model-len",
        env.get("MAX_MODEL_LEN", profile["max_model_len"]),
        "--gpu-memory-utilization",
        env.get("GPU_MEMORY_UTILIZATION", profile["gpu_memory_utilization"]),
        "--max-num-seqs",
        env.get("MAX_NUM_SEQS", profile["max_num_seqs"]),
    ]
    if env.get("VLLM_TOOL_CALL_PARSER"):
        command.extend(["--enable-auto-tool-choice", "--tool-call-parser", env["VLLM_TOOL_CALL_PARSER"]])
    if env.get("VLLM_CHAT_TEMPLATE"):
        command.extend(["--chat-template", env["VLLM_CHAT_TEMPLATE"]])
    if env.get("VLLM_API_KEY"):
        command.extend(["--api-key", env["VLLM_API_KEY"]])
    return command


def redacted(command: list[str]) -> list[str]:
    result, hide = [], False
    for part in command:
        result.append("***" if hide else part)
        hide = part == "--api-key"
    return result


def main() -> int:
    env = dict(os.environ)
    command = build_command(env)
    port = resolve_port(env)
    extra = runtime_environment(env)
    settings = {
        "command": redacted(command),
        "port": port,
        "port_source": "CDSW_APP_PORT" if env.get("CDSW_APP_PORT", "").strip() else "fallback",
        "extra_environment": extra,
    }
    print("vLLM Application startup configuration: " + json.dumps(settings), file=sys.stderr, flush=True)
    return run_supervised(
        command,
        env={**env, **extra},
        readiness=lambda: http_ready(f"http://127.0.0.1:{port}/health"),
        startup_timeout=float(env.get("APP_STARTUP_TIMEOUT_MINUTES", "15")) * 60,
    )


if __name__ == "__main__":
    raise SystemExit(main())
