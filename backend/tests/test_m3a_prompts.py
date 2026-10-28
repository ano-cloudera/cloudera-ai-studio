from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base, ProjectRow, PromptVersionRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.prompt_management.keys import ASK_DATA_SYSTEM, RAG_SYSTEM
from app.prompt_management.resolver import PromptResolver
from app.prompt_management.sources import FilePromptSource
from app.services.prompt_service import PromptService

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres M3A integration tests",
)


@pytest.fixture()
def m3a_client():
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return TestClient(create_app(settings)), factory


def test_resolver_file_fallback_without_db():
    settings = Settings(_env_file=None, state_store="sqlite")
    effective = PromptResolver(settings, session=None).resolve(ASK_DATA_SYSTEM)
    assert effective.source == "file"
    assert effective.content.strip() == (FilePromptSource().get(ASK_DATA_SYSTEM) or "").strip()
    assert len(effective.content) > 20


def test_prompt_crud_publish_rollback(m3a_client):
    client, factory = m3a_client
    create = client.post(
        "/api/v1/prompts",
        json={
            "name": "Test Ask Data",
            "key": f"test.ask_data.system.{uuid.uuid4().hex[:8]}",
            "scope": "global",
            "initial_content": "GLOBAL V1",
        },
    )
    assert create.status_code == 200, create.text
    prompt_id = create.json()["prompt"]["id"]
    versions = client.get(f"/api/v1/prompts/{prompt_id}/versions").json()["versions"]
    assert len(versions) == 1
    assert versions[0]["status"] == "DRAFT"
    v1_id = versions[0]["id"]

    pub = client.post(f"/api/v1/prompts/{prompt_id}/versions/{v1_id}/publish")
    assert pub.status_code == 200
    assert pub.json()["version"]["status"] == "ACTIVE"

    v2 = client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        json={"content": "GLOBAL V2"},
    )
    v2_id = v2.json()["version"]["id"]
    client.post(f"/api/v1/prompts/{prompt_id}/versions/{v2_id}/publish")
    client.post(f"/api/v1/prompts/{prompt_id}/versions/{v1_id}/rollback")

    with factory() as session:
        svc = PromptService(session)
        row = svc.get_prompt(uuid.UUID(prompt_id))
        active = session.get(PromptVersionRow, row.active_version_id)
        assert active is not None
        assert active.content == "GLOBAL V1"
        statuses = {v.status for v in svc.list_versions(uuid.UUID(prompt_id))}
        assert "ARCHIVED" in statuses
        assert "ACTIVE" in statuses


def test_project_isolation(m3a_client):
    client, factory = m3a_client
    with factory() as session:
        _ws, default_project = ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        ws_id = default_project.workspace_id
        project_a = default_project.id
        project_b = ProjectRow(
            workspace_id=ws_id,
            slug=f"isolation-{uuid.uuid4().hex[:8]}",
            name="Isolation B",
            ossie_root_path="projects/reference_impala",
            status="active",
        )
        session.add(project_b)
        session.commit()
        project_b_id = project_b.id

    iso_key = f"test.isolation.{uuid.uuid4().hex[:8]}"

    def create_project_prompt(project_id: uuid.UUID, content: str) -> None:
        resp = client.post(
            "/api/v1/prompts",
            json={
                "name": f"Proj {project_id}",
                "key": iso_key,
                "scope": "project",
                "workspace_id": str(ws_id),
                "project_id": str(project_id),
                "initial_content": content,
            },
        )
        assert resp.status_code == 200, resp.text
        pid = uuid.UUID(resp.json()["prompt"]["id"])
        if project_id == project_a:
            vid = client.get(f"/api/v1/prompts/{pid}/versions").json()["versions"][0]["id"]
            client.post(f"/api/v1/prompts/{pid}/versions/{vid}/publish")
        else:
            with factory() as session:
                svc = PromptService(session)
                vid = svc.list_versions(pid)[0].id
                svc.publish_version(pid, vid)
                session.commit()

    create_project_prompt(project_a, "PROJECT A OVERRIDE")
    create_project_prompt(project_b_id, "PROJECT B OVERRIDE")

    resolve_a = client.post("/api/v1/prompts/resolve", json={"prompt_key": iso_key, "project_id": str(project_a)})
    resolve_b = client.post("/api/v1/prompts/resolve", json={"prompt_key": iso_key, "project_id": str(project_b_id)})
    assert resolve_a.json()["content"] == "PROJECT A OVERRIDE"
    assert resolve_b.json()["content"] == "PROJECT B OVERRIDE"
    assert resolve_a.json()["source"] == "project"


def test_resolve_precedence_project_over_global(m3a_client):
    client, factory = m3a_client
    key = f"test.precedence.{uuid.uuid4().hex[:8]}"
    g = client.post(
        "/api/v1/prompts",
        json={"name": "Global RAG", "key": key, "scope": "global", "initial_content": "GLOBAL RAG"},
    )
    g_id = g.json()["prompt"]["id"]
    g_v = client.get(f"/api/v1/prompts/{g_id}/versions").json()["versions"][0]["id"]
    client.post(f"/api/v1/prompts/{g_id}/versions/{g_v}/publish")

    with factory() as session:
        _ws, project = ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        ws_id = project.workspace_id
        project_id = project.id

    p = client.post(
        "/api/v1/prompts",
        json={
            "name": "Project RAG",
            "key": key,
            "scope": "project",
            "workspace_id": str(ws_id),
            "project_id": str(project_id),
            "initial_content": "PROJECT RAG",
        },
    )
    p_id = p.json()["prompt"]["id"]
    p_v = client.get(f"/api/v1/prompts/{p_id}/versions").json()["versions"][0]["id"]
    client.post(f"/api/v1/prompts/{p_id}/versions/{p_v}/publish")

    resolved = client.post(
        "/api/v1/prompts/resolve",
        json={"prompt_key": key, "project_id": str(project_id)},
    )
    body = resolved.json()
    assert body["source"] == "project"
    assert body["content"] == "PROJECT RAG"
    assert body["chain"][-1] == "project"


def _run_backend_script(script: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def test_seed_idempotent(m3a_client):
    script = BACKEND_ROOT / "scripts" / "seed_prompts.py"
    for _ in range(2):
        proc = _run_backend_script(script)
        assert proc.returncode == 0, proc.stderr
