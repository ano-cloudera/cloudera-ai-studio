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


def test_no_special_runtime_is_needed_for_the_gpu() -> None:
    assert llm.preflight({"VLLM_MODEL_ID": "Qwen/Other-9B"}, 100 * GB) == ([], [])


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
    assert "--language-model-only" not in command and "--max-cudagraph-capture-size" not in command  # opt-in only
    more = app.build_command({**env, "VLLM_LANGUAGE_MODEL_ONLY": "true", "VLLM_MAX_CUDAGRAPH_CAPTURE_SIZE": "16"})
    assert "--language-model-only" in more and more[more.index("--max-cudagraph-capture-size") + 1] == "16"
    try:
        app.build_command({**env, "VLLM_DEFAULT_CHAT_TEMPLATE_KWARGS": "not json"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid JSON must be refused before the Application starts")


def _fake_registry(assignments):
    """A Backend double: stores providers/models, answers the registry routes the registration uses."""
    state = {"providers": [], "models": [], "puts": []}

    def call(method, path, body=None):
        if path == "/api/v1/ai/providers" and method == "GET":
            return {"providers": state["providers"]}
        if path == "/api/v1/ai/providers" and method == "POST":
            row = {**body, "id": "p1"}
            state["providers"].append(row)
            return {"provider": row}
        if path.startswith("/api/v1/ai/providers/") and method == "PATCH":
            state["providers"][0].update(body)
            return {"provider": state["providers"][0]}
        if path == "/api/v1/ai/models" and method == "GET":
            return {"models": state["models"]}
        if path == "/api/v1/ai/models" and method == "POST":
            row = {**body, "id": "m1"}
            state["models"].append(row)
            return {"model": row}
        if path.startswith("/api/v1/ai/models/") and method == "PATCH":
            state["models"][0].update(body)
            return {"model": state["models"][0]}
        if path.startswith("/api/v1/ai/models/") and path.endswith("/test"):
            return {"status": "READY"}
        if path == "/api/v1/ai/assignments" and method == "GET":
            return {"assignments": assignments}
        if path.startswith("/api/v1/ai/assignments/") and method == "PUT":
            state["puts"].append(path.rsplit("/", 1)[1])
            return {"assignment": {}}
        raise AssertionError((method, path))

    return call, state


def _register_module():
    spec = importlib.util.spec_from_file_location("amp_register_llm", REPO / "scripts" / "amp" / "register_llm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_registration_gives_the_model_only_to_capabilities_nobody_chose() -> None:
    reg = _register_module()
    assignments = [
        {"capability": "ASK_DATA", "source": "PROJECT", "model_id": "chosen"},
        {"capability": "CHAT_DEFAULT", "source": "LEGACY_FALLBACK", "model_id": None},
        {"capability": "RAG_GENERATION", "source": "LEGACY_FALLBACK", "model_id": None},
    ]
    call, state = _fake_registry(assignments)
    result = reg.register(call, base_url="https://x-vllm.d/v1", name="M (vLLM)", served_name="studio-llm", context_window=32768)
    assert "ASK_DATA" not in state["puts"] and set(state["puts"]) == {"CHAT_DEFAULT", "RAG_GENERATION", "SKILLS"}
    assert result["status"] == "READY"
    provider = state["providers"][0]
    assert provider["provider_type"] == "OPENAI_COMPATIBLE" and provider["secret_ref"] == "env://VLLM_API_KEY"
    assert provider["config_json"] == {"guided_json": True, "disable_thinking": True}
    assert state["models"][0]["model_id"] == "studio-llm" and state["models"][0]["context_window"] == 32768


def test_registering_twice_updates_instead_of_duplicating() -> None:
    reg = _register_module()
    call, state = _fake_registry([])
    for _ in range(2):
        reg.register(call, base_url="https://x-vllm.d/v1", name="M (vLLM)", served_name="studio-llm", context_window=None)
    assert len(state["providers"]) == 1 and len(state["models"]) == 1


def test_the_vllm_key_is_derived_and_the_application_is_reachable_by_the_backend() -> None:
    import yaml

    spec = importlib.util.spec_from_file_location("amp_deploy2", REPO / "scripts" / "amp" / "deploy.py")
    dep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dep)
    out = dep.with_studio_secrets({"CAI_DATA_DIR": "/tmp/anywhere-test-secret-dir"})
    assert out["VLLM_API_KEY"] and out["VLLM_API_KEY"] != out["STUDIO_API_TOKEN"]
    manifest = yaml.safe_load((REPO / "deployment/cai/manifests/applications.yaml").read_text(encoding="utf-8"))
    apps = {a["key"]: a for a in manifest["applications"]}
    assert apps["vllm"]["bypass_authentication"] is True  # the Backend calls it without a Cloudera AI login
    assert "VLLM_API_KEY" in apps["backend"]["forward_env"] and "VLLM_API_KEY" in apps["vllm"]["forward_env"]


def test_the_keys_it_registers_pass_the_registrys_own_key_rules() -> None:
    from app.ai_registry.validation import validate_model_key, validate_provider_key

    reg = _register_module()
    validate_provider_key(reg.PROVIDER_KEY)
    validate_model_key(reg.MODEL_KEY)
