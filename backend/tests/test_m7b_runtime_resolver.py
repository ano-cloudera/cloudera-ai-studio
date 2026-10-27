from __future__ import annotations

import os
import uuid
import pytest

from app.ai_registry.hybrid_provider_registry import HybridProviderRegistry
from app.ai_registry.runtime_errors import RegistryRuntimeError
from app.ai_registry.runtime_resolver import RuntimeModelResolver
from app.core.config import Settings
from app.db.platform_models import AiModelRow, AiProviderRow, ModelAssignmentRow
from app.llm.registry import ProviderRegistry
from pydantic import SecretStr

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture()
def resolver_session():
    from app.db.platform_engine import get_session_factory
    from app.projects.bootstrap import ensure_platform_seed
    from tests.alembic_schema_helpers import clear_model_assignments, ensure_alembic_head

    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    ensure_alembic_head(url)
    clear_model_assignments(engine)
    factory = get_session_factory(url)
    with factory() as session:
        from app.core.config import BACKEND_ROOT

        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        yield session, factory


def test_runtime_resolver_legacy_when_no_assignment(resolver_session):
    session, _ = resolver_session
    from app.projects.resolver import load_default_project

    settings = Settings(_env_file=None, state_store="postgres", database_url=os.environ["DATABASE_URL"])
    project = load_default_project(settings)
    assert project is not None
    resolver = RuntimeModelResolver(session)
    out = resolver.resolve(
        capability="ASK_DATA",
        workspace_id=project.workspace_id,
        project_id=project.id,
        fallback_provider="qwen",
        fallback_model="legacy-model",
    )
    assert out.source == "LEGACY_FALLBACK"
    assert out.legacy_model == "legacy-model"


def test_project_assignment_over_workspace(resolver_session):
    session, factory = resolver_session
    from app.projects.resolver import load_default_project

    settings = Settings(_env_file=None, state_store="postgres", database_url=os.environ["DATABASE_URL"])
    project = load_default_project(settings)
    assert project is not None
    ws = project.workspace_id
    proj = project.id
    p_ws = AiProviderRow(
        workspace_id=ws,
        project_id=None,
        name="WS Provider",
        key=f"ws_{uuid.uuid4().hex[:6]}",
        provider_type="OPENAI_COMPATIBLE",
        base_url="http://127.0.0.1:1/v1",
        enabled=True,
    )
    p_proj = AiProviderRow(
        workspace_id=ws,
        project_id=proj,
        name="Proj Provider",
        key=f"proj_{uuid.uuid4().hex[:6]}",
        provider_type="OPENAI_COMPATIBLE",
        base_url="http://127.0.0.1:2/v1",
        enabled=True,
    )
    session.add_all([p_ws, p_proj])
    session.flush()
    m_ws = AiModelRow(
        provider_id=p_ws.id,
        workspace_id=ws,
        project_id=None,
        name="WS Model",
        key=f"ws_m_{uuid.uuid4().hex[:6]}",
        model_id="ws-model-id",
        model_type="CHAT",
        enabled=True,
    )
    m_proj = AiModelRow(
        provider_id=p_proj.id,
        workspace_id=ws,
        project_id=proj,
        name="Proj Model",
        key=f"proj_m_{uuid.uuid4().hex[:6]}",
        model_id="proj-model-id",
        model_type="CHAT",
        enabled=True,
    )
    session.add_all([m_ws, m_proj])
    session.flush()
    session.add_all(
        [
            ModelAssignmentRow(workspace_id=ws, project_id=None, capability="ASK_DATA", model_id=m_ws.id, enabled=True),
            ModelAssignmentRow(workspace_id=ws, project_id=proj, capability="ASK_DATA", model_id=m_proj.id, enabled=True),
        ]
    )
    session.commit()

    with factory() as s2:
        resolver = RuntimeModelResolver(s2)
        out = resolver.resolve(
            capability="ASK_DATA",
            workspace_id=ws,
            project_id=proj,
            fallback_provider="qwen",
            fallback_model="legacy",
        )
        assert out.source == "PROJECT"
        assert out.runtime_model_id == "proj-model-id"


def test_disabled_assignment_raises(resolver_session):
    session, _ = resolver_session
    from app.projects.resolver import load_default_project

    settings = Settings(_env_file=None, state_store="postgres", database_url=os.environ["DATABASE_URL"])
    project = load_default_project(settings)
    assert project is not None
    provider = AiProviderRow(
        workspace_id=project.workspace_id,
        project_id=project.id,
        name="Disabled",
        key=f"dis_{uuid.uuid4().hex[:6]}",
        provider_type="OPENAI_COMPATIBLE",
        base_url="http://127.0.0.1:3/v1",
        enabled=True,
    )
    session.add(provider)
    session.flush()
    model = AiModelRow(
        provider_id=provider.id,
        workspace_id=project.workspace_id,
        project_id=project.id,
        name="Disabled Model",
        key=f"dis_m_{uuid.uuid4().hex[:6]}",
        model_id="x",
        model_type="CHAT",
        enabled=False,
    )
    session.add(model)
    session.flush()
    session.add(
        ModelAssignmentRow(
            workspace_id=project.workspace_id,
            project_id=project.id,
            capability="ASK_DATA",
            model_id=model.id,
            enabled=True,
        )
    )
    session.commit()
    resolver = RuntimeModelResolver(session)
    with pytest.raises(RegistryRuntimeError) as exc:
        resolver.resolve(
            capability="ASK_DATA",
            workspace_id=project.workspace_id,
            project_id=project.id,
            fallback_provider="qwen",
            fallback_model="legacy",
        )
    assert exc.value.code == "MODEL_DISABLED"


def test_hybrid_registry_uses_legacy_without_postgres_session():
    settings = Settings.model_construct(
        qwen_base_url="https://qwen/v1",
        qwen_api_key=SecretStr("t"),
        qwen_model="qwen-1",
        gemini_api_key=SecretStr(""),
        openai_api_key=SecretStr(""),
    )
    hybrid = HybridProviderRegistry(settings, legacy=ProviderRegistry(settings), session_factory=None)
    resolution = hybrid.prepare_request(
        capability="ASK_DATA",
        workspace_id=None,
        project_id=None,
        fallback_provider="qwen",
        fallback_model="qwen-1",
    )
    assert resolution.source == "LEGACY_FALLBACK"
    provider = hybrid.resolve("qwen", "qwen-1")
    assert provider is not None
