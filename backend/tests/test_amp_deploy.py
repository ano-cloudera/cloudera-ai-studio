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
    assert client.calls[0][2]["bypass_authentication"] is False
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
