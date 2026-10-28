from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

_CAI = Path(__file__).resolve().parents[2]
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
    return path


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
    if env.get("VLLM_API_KEY"):
        command.extend(["--api-key", env["VLLM_API_KEY"]])
    return command


def main() -> int:
    env = dict(os.environ)
    command = build_command(env)
    port = resolve_port(env)
    print("vLLM startup: " + json.dumps({"port": port}), file=sys.stderr, flush=True)
    return run_supervised(
        command,
        env=env,
        readiness=lambda: http_ready(f"http://127.0.0.1:{port}/health"),
        startup_timeout=float(env.get("APP_STARTUP_TIMEOUT_MINUTES", "15")) * 60,
    )


if __name__ == "__main__":
    raise SystemExit(main())
