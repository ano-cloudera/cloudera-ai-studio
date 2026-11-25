from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("amp_llm", REPO / "scripts" / "amp" / "llm.py")
llm = importlib.util.module_from_spec(_spec)
sys.modules["amp_llm"] = llm
_spec.loader.exec_module(llm)

GB = 1024**3


def test_defaults_fill_what_the_project_left_out_and_never_override_it() -> None:
    env = llm.apply_defaults({"VLLM_MODEL_ID": "Qwen/Other-9B", "GPU_PROFILE": "  "})
    assert env["VLLM_MODEL_ID"] == "Qwen/Other-9B"  # a project value wins
    assert env["GPU_PROFILE"] == "l40s" and env["ENABLE_VLLM"] == "true" and env["VLLM_TOOL_CALL_PARSER"] == "hermes"


def test_a_model_id_without_an_org_stops_the_job() -> None:
    problems, _ = llm.preflight({"VLLM_MODEL_ID": "qwen"}, 100 * GB)
    assert problems and "Hugging Face id" in problems[0]


def test_too_little_disk_stops_the_job_unless_the_weights_are_already_there(tmp_path) -> None:
    env = {"VLLM_MODEL_ID": "Qwen/Other-9B", "MODEL_PATH": str(tmp_path / "m"), "AMP_VLLM_RUNTIME_ID": "gpu"}
    assert llm.preflight(env, 5 * GB)[0]
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "config.json").write_text("{}")
    assert llm.preflight(env, 5 * GB) == ([], [])


def test_a_missing_gpu_runtime_is_a_warning_not_a_stop() -> None:
    problems, warnings = llm.preflight({"VLLM_MODEL_ID": "Qwen/Other-9B"}, 100 * GB)
    assert not problems and any("AMP_VLLM_RUNTIME_ID" in w for w in warnings)
