from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("amp_deploy", REPO / "scripts" / "amp" / "deploy.py")
deploy = importlib.util.module_from_spec(_spec)
sys.modules["amp_deploy"] = deploy
_spec.loader.exec_module(deploy)

ENV = {
    "CDSW_DOMAIN": "ml-1.example.site",
    "CDSW_PROJECT_ID": "p1",
    "GEMINI_API_KEY": "secret-gemini",
    "TRINO_PASSWORD": "secret-trino",
    "AMP_FORWARD_ENV": "MY_POC_TOKEN",
    "MY_POC_TOKEN": "secret-poc",
}


class FakeClient:
    def __init__(self, existing=None, statuses=("APPLICATION_STARTING", "APPLICATION_RUNNING")):
        self.project_id = "p1"
        self.existing = existing or []
        self.calls: list[tuple] = []
        self.statuses = list(statuses)

    def list_applications(self):
        return self.existing

    def detect_runtime(self):
        return getattr(self, "runtime", "")

    def create_application(self, payload):
        self.calls.append(("create", payload["subdomain"], payload))
        return {"id": f"id-{payload['subdomain']}"}

    def update_application(self, app_id, payload):
        self.calls.append(("update", app_id, payload))

    def restart_application(self, app_id):
        self.calls.append(("restart", app_id))

    def get_application(self, app_id):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"id": app_id, "name": app_id, "status": status}


def _plan(only=None):
    return deploy.build_plan(deploy.load_manifest(), ENV, only)


def test_plan_covers_the_three_default_applications_in_order() -> None:
    plan = _plan()
    assert [p["subdomain"] for p in plan] == ["anywhere-qdrant", "anywhere-backend", "anywhere-frontend"]
    backend = plan[1]["environment"]
    assert backend["QDRANT_URL"] == "https://anywhere-qdrant.ml-1.example.site:443"
    assert backend["GEMINI_API_KEY"] == "secret-gemini" and backend["MY_POC_TOKEN"] == "secret-poc"
    assert plan[2]["environment"]["BACKEND_API_URL"] == "https://anywhere-backend.ml-1.example.site"
    assert "GEMINI_API_KEY" not in plan[0]["environment"] and "GEMINI_API_KEY" not in plan[2]["environment"]
    assert [p["key"] for p in _plan("vllm")] == ["vllm"]


def test_new_applications_are_created_and_existing_ones_updated_and_restarted() -> None:
    client = FakeClient(existing=[{"id": "b1", "subdomain": "anywhere-backend"}])
    logs: list[str] = []
    deploy.deploy(client, _plan(), ENV, skip_build=True, timeout=60, log=logs.append, sleep=lambda _: None)
    kinds = [c[0] for c in client.calls]
    assert kinds == ["create", "update", "restart", "create"]
    assert client.calls[0][2]["bypass_authentication"] is True  # Qdrant is called server to server
    assert client.calls[2][2]["bypass_authentication"] is False  # the Frontend keeps the login
    assert any("running at https://anywhere-backend.ml-1.example.site" in line for line in logs)


def test_a_failed_or_stuck_application_stops_the_run() -> None:
    with pytest.raises(deploy.ApiError):
        deploy.wait_running(FakeClient(statuses=("APPLICATION_FAILED",)), "x", 5, sleep=lambda _: None)
    with pytest.raises(deploy.ApiError):
        deploy.wait_running(FakeClient(statuses=("APPLICATION_STARTING",)), "x", 0.0, sleep=lambda _: None)


def test_client_sends_a_bearer_token_and_reads_pages() -> None:
    seen = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(self.body).encode()

    pages = [{"applications": [{"id": "1"}], "next_page_token": "t"}, {"applications": [{"id": "2"}]}]

    def opener(req, timeout):
        seen.append((req.get_method(), req.full_url, req.headers.get("Authorization")))
        return Resp(pages.pop(0))

    client = deploy.Cml("d.example", "p1", "tok", opener=opener)
    assert [a["id"] for a in client.list_applications()] == ["1", "2"]
    assert seen[0][2] == "Bearer tok" and seen[0][1].startswith("https://d.example/api/v2/projects/p1/applications")


def test_dry_run_prints_names_never_values(capsys, monkeypatch) -> None:
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    assert deploy.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "GEMINI_API_KEY" in out and "secret-gemini" not in out and "secret-trino" not in out


def test_vllm_is_created_only_when_enabled_and_gets_its_gpu_runtime() -> None:
    assert "vllm" not in [p["key"] for p in _plan()]
    env = {**ENV, "ENABLE_VLLM": "true", "VLLM_MODEL_ID": "org/some-model", "AMP_VLLM_RUNTIME_ID": "gpu-rt", "AMP_RUNTIME_ID": "std-rt", "GPU_PROFILE": "l40s"}
    plan = deploy.build_plan(deploy.load_manifest(), env)
    vllm = plan[-1]
    assert vllm["key"] == "vllm" and vllm["nvidia_gpu"] == 1
    assert vllm["environment"]["MODEL_PATH"] == "/home/cdsw/models/some-model"
    assert vllm["environment"]["GPU_PROFILE"] == "l40s"
    assert deploy.payload_for(vllm, vllm["runtime_id"])["runtime_identifier"] == "gpu-rt"
    client = FakeClient()
    logs: list[str] = []
    deploy.deploy(client, [vllm], env, skip_build=True, timeout=60, log=logs.append, sleep=lambda _: None)
    created = client.calls[0][2]
    assert created["nvidia_gpu"] == 1 and created["runtime_identifier"] == "gpu-rt"
    assert any("OpenAI-compatible" in line for line in logs)


def test_a_gpu_application_without_a_gpu_runtime_warns() -> None:
    env = {**ENV, "ENABLE_VLLM": "true"}
    plan = deploy.build_plan(deploy.load_manifest(), env, "vllm")
    logs: list[str] = []
    deploy.deploy(FakeClient(), plan, env, skip_build=True, timeout=60, log=logs.append, sleep=lambda _: None)
    assert any("AMP_VLLM_RUNTIME_ID" in line for line in logs)


def test_resources_come_from_the_manifest_and_can_be_overridden_per_poc() -> None:
    base = {p["key"]: p for p in _plan()}
    assert (base["backend"]["cpu"], base["backend"]["memory"], base["backend"]["nvidia_gpu"]) == (4, 16, 0)
    env = {**ENV, "AMP_BACKEND_CPU": "8", "AMP_BACKEND_MEMORY_GB": "32"}
    big = {p["key"]: p for p in deploy.build_plan(deploy.load_manifest(), env)}
    assert (big["backend"]["cpu"], big["backend"]["memory"]) == (8, 32)
    assert big["qdrant"]["cpu"] == 4
    payload = deploy.payload_for(big["backend"])
    assert payload["cpu"] == 8 and payload["memory"] == 32


def test_main_ignores_the_arguments_an_ipython_kernel_adds() -> None:
    assert deploy.main(["-f", "/tmp/jupyter/runtime/kernel-1.json", "--dry-run"]) == 0


def test_the_runtime_of_the_projects_jobs_is_used_when_none_is_configured() -> None:
    client = FakeClient()
    client.runtime = "detected-rt"
    deploy.deploy(client, _plan("qdrant"), ENV, skip_build=True, timeout=60, log=lambda _: None, sleep=lambda _: None)
    assert client.calls[0][2]["runtime_identifier"] == "detected-rt"
    explicit = FakeClient()
    explicit.runtime = "detected-rt"
    deploy.deploy(explicit, _plan("qdrant"), {**ENV, "AMP_RUNTIME_ID": "chosen-rt"}, skip_build=True, timeout=60, log=lambda _: None, sleep=lambda _: None)
    assert explicit.calls[0][2]["runtime_identifier"] == "chosen-rt"


def test_client_detects_the_runtime_from_the_jobs_list() -> None:
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"jobs": [{"name": "a"}, {"name": "b", "runtime_identifier": "img:1"}]}).encode()

    client = deploy.Cml("d.example", "p1", "tok", opener=lambda req, timeout: Resp())
    assert client.detect_runtime() == "img:1"


def test_non_string_project_variables_are_reported_by_name_only() -> None:
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"environment": json.dumps({"OK": "x", "BAD": {"a": 1}, "ALSO": 3})}).encode()

    client = deploy.Cml("d.example", "p1", "tok", opener=lambda req, timeout: Resp())
    assert client.non_string_project_variables() == ["ALSO", "BAD"]


def test_set_env_stores_the_broken_variables_as_plain_text() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("amp_set_env", REPO / "scripts" / "amp" / "set_env.py")
    set_env = importlib.util.module_from_spec(spec)
    sys.modules["amp_set_env"] = set_env
    spec.loader.exec_module(set_env)

    class Client:
        def __init__(self):
            self.saved = None

        def project_variables(self):
            return {"OK": "x", "GEMINI_API_KEY": {"a": 1}, "ENABLE_VLLM": {"a": 1}}

        def set_project_variables(self, variables):
            self.saved = variables

    client = Client()
    answers = {"GEMINI_API_KEY": "key-1", "ENABLE_VLLM": "false"}
    done = set_env.repair(client, [], lambda name, default: answers[name], {})
    assert done == ["ENABLE_VLLM", "GEMINI_API_KEY"]
    assert client.saved == {"OK": "x", "GEMINI_API_KEY": "key-1", "ENABLE_VLLM": "false"}
    assert all(isinstance(v, str) for v in client.saved.values())


def test_backend_and_qdrant_skip_the_login_and_the_frontend_keeps_it() -> None:
    bypass = {item["key"]: item["bypass_authentication"] for item in _plan()}
    assert bypass == {"qdrant": True, "backend": True, "frontend": False}
    assert deploy.payload_for(_plan("backend")[0])["bypass_authentication"] is True
    kept = {item["key"]: item["bypass_authentication"] for item in deploy.build_plan(deploy.load_manifest(), {**ENV, "AMP_REQUIRE_LOGIN": "backend"})}
    assert kept["backend"] is False and kept["qdrant"] is True
