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
    assert env["GPU_PROFILE"] == "l40s" and env["ENABLE_VLLM"] == "true" and env["VLLM_TOOL_CALL_PARSER"] == "qwen3_coder"
    assert env["VLLM_REASONING_PARSER"] == "qwen3" and "false" in env["VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS"]


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


def test_the_launcher_passes_the_reasoning_parser_and_thinking_switch(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location("studio_vllm_app", REPO / "deployment" / "cai" / "launchers" / "studio-vllm" / "app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    (tmp_path / "config.json").write_text("{}")
    env = {"MODEL_PATH": str(tmp_path), "GPU_PROFILE": "l40s", "VLLM_REASONING_PARSER": "qwen3",
           "VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS": '{"enable_thinking": false}', "VLLM_TOOL_CALL_PARSER": "qwen3_coder"}
    command = app.build_command(env)
    assert command[command.index("--reasoning-parser") + 1] == "qwen3"
    assert command[command.index("--default-chat-template-kwargs") + 1] == '{"enable_thinking": false}'
    assert command[command.index("--tool-call-parser") + 1] == "qwen3_coder"
    try:
        app.build_command({**env, "VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS": "not json"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid JSON must be refused before the Application starts")
