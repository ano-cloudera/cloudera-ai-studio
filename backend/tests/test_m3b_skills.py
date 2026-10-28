from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base, ProjectRow, SkillVersionRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.services.skill_service import SkillService
from app.skills.resolver import SkillResolver
from app.skills.tool_registry import ToolRegistry

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres M3B integration tests",
)


@pytest.fixture()
def m3b_client():
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


def test_tool_registry_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown tools"):
        ToolRegistry.validate_tool_keys(["not_a_tool"])


def test_skill_crud_publish_rollback(m3b_client):
    client, factory = m3b_client
    key = f"test.skill.{uuid.uuid4().hex[:8]}"
    create = client.post(
        "/api/v1/skills",
        json={
            "name": "Test Skill",
            "key": key,
            "scope": "workspace",
            "instructions": "Do work",
            "allowed_tools": [],
            "config": {"handler_type": "prompt_only"},
        },
    )
    assert create.status_code == 200, create.text
    skill_id = create.json()["skill"]["id"]
    versions = client.get(f"/api/v1/skills/{skill_id}/versions").json()["versions"]
    v1_id = versions[0]["id"]
    pub = client.post(f"/api/v1/skills/{skill_id}/versions/{v1_id}/publish")
    assert pub.json()["version"]["status"] == "ACTIVE"

    v2 = client.post(
        f"/api/v1/skills/{skill_id}/versions",
        json={"instructions": "v2", "allowed_tools": [], "config": {"handler_type": "prompt_only"}},
    )
    v2_id = v2.json()["version"]["id"]
    client.post(f"/api/v1/skills/{skill_id}/versions/{v2_id}/publish")
    client.post(f"/api/v1/skills/{skill_id}/versions/{v1_id}/rollback")

    with factory() as session:
        svc = SkillService(session)
        row = svc.get_skill(uuid.UUID(skill_id))
        active = session.get(SkillVersionRow, row.active_version_id)
        assert active.instructions == "Do work"


def test_invalid_tool_on_create(m3b_client):
    client, _ = m3b_client
    resp = client.post(
        "/api/v1/skills",
        json={
            "name": "Bad",
            "key": f"bad.{uuid.uuid4().hex[:8]}",
            "scope": "workspace",
            "allowed_tools": ["shell_exec"],
            "config": {"handler_type": "prompt_only"},
        },
    )
    assert resp.status_code == 422


def test_draft_cannot_execute(m3b_client):
    client, _ = m3b_client
    key = f"draft.{uuid.uuid4().hex[:8]}"
    skill_id = client.post(
        "/api/v1/skills",
        json={
            "name": "Draft",
            "key": key,
            "scope": "workspace",
            "allowed_tools": [],
            "config": {"handler_type": "prompt_only"},
        },
    ).json()["skill"]["id"]
    exec_resp = client.post(f"/api/v1/skills/{skill_id}/execute", json={"input": "hello"})
    assert exec_resp.status_code == 409


def test_project_isolation_resolver(m3b_client):
    client, factory = m3b_client
    iso_key = f"iso.skill.{uuid.uuid4().hex[:8]}"
    with factory() as session:
        _ws, default_project = ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        ws_id = default_project.workspace_id
        project_a = default_project.id
        project_b = ProjectRow(
            workspace_id=ws_id,
            slug=f"skill-iso-{uuid.uuid4().hex[:8]}",
            name="B",
            ossie_root_path="projects/reference_impala",
            status="active",
        )
        session.add(project_b)
        session.commit()
        project_b_id = project_b.id

    def create_project_skill(project_id: uuid.UUID, instructions: str) -> None:
        resp = client.post(
            "/api/v1/skills",
            json={
                "name": "P",
                "key": iso_key,
                "scope": "project",
                "workspace_id": str(ws_id),
                "project_id": str(project_id),
                "instructions": instructions,
                "allowed_tools": [],
                "config": {"handler_type": "prompt_only"},
            },
        )
        assert resp.status_code == 200, resp.text
        sid = uuid.UUID(resp.json()["skill"]["id"])
        if project_id == project_a:
            vid = client.get(f"/api/v1/skills/{sid}/versions").json()["versions"][0]["id"]
            client.post(f"/api/v1/skills/{sid}/versions/{vid}/publish")
        else:
            with factory() as session:
                svc = SkillService(session)
                vid = svc.list_versions(sid)[0].id
                svc.publish_version(sid, vid)
                session.commit()

    create_project_skill(project_a, "A")
    create_project_skill(project_b_id, "B")

    with factory() as session:
        resolver = SkillResolver(session)
        ra = resolver.resolve(iso_key, workspace_id=ws_id, project_id=project_a)
        rb = resolver.resolve(iso_key, workspace_id=ws_id, project_id=project_b_id)
        assert ra and ra.version.instructions == "A"
        assert rb and rb.version.instructions == "B"


def test_execute_prompt_only_mock(m3b_client):
    client, _ = m3b_client
    key = f"exec.{uuid.uuid4().hex[:8]}"
    skill_id = client.post(
        "/api/v1/skills",
        json={
            "name": "Exec",
            "key": key,
            "scope": "workspace",
            "instructions": "Be brief",
            "allowed_tools": [],
            "config": {"handler_type": "prompt_only"},
        },
    ).json()["skill"]["id"]
    vid = client.get(f"/api/v1/skills/{skill_id}/versions").json()["versions"][0]["id"]
    client.post(f"/api/v1/skills/{skill_id}/versions/{vid}/publish")

    class FakeOut:
        answer = "mocked skill answer"

    fake_provider = AsyncMock()
    fake_provider.generate_structured = AsyncMock(return_value=FakeOut())

    from unittest.mock import MagicMock

    from app.ai_registry.hybrid_provider_registry import HybridProviderRegistry

    mock_registry = MagicMock(spec=HybridProviderRegistry)
    mock_registry.prepare_request = MagicMock()
    mock_registry.resolve = MagicMock(return_value=fake_provider)
    mock_registry.clear_request_context = MagicMock()
    client.app.state.chat_service.dependencies.provider_registry = mock_registry

    resp = client.post(f"/api/v1/skills/{skill_id}/execute", json={"input": "What is 2+2?"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"]["answer"] == "mocked skill answer"
    assert body["execution"]["handler_type"] == "prompt_only"
    assert body["execution"]["skill_version"] == 1


def test_list_tools_api(m3b_client):
    client, _ = m3b_client
    resp = client.get("/api/v1/tools")
    assert resp.status_code == 200
    keys = {t["key"] for t in resp.json()["tools"]}
    assert "ask_data" in keys
    assert "rag_search" in keys


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


def test_seed_skills_idempotent(m3b_client):
    script = BACKEND_ROOT / "scripts" / "seed_skills.py"
    for _ in range(2):
        proc = _run_backend_script(script)
        assert proc.returncode == 0, proc.stderr
