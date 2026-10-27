"""Phase 3 — real /chat governed semantic path (Golden Banking)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

requires_integration = pytest.mark.skipif(
    os.environ.get("GOLDEN_BANKING_RUN_INTEGRATION", "1") != "1",
    reason="Set GOLDEN_BANKING_RUN_INTEGRATION=1",
)


@requires_integration
def test_phase3_chat_governed_evidence_script():
    script = ROOT / "scripts/demo/phase3_chat_governed_evidence.py"
    env = os.environ.copy()
    env.setdefault("BANKING_DEMO_PG_PASSWORD", "m1pass")
    proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    out = ROOT / "testing/evidence/golden-path/PHASE3-SEMANTIC/chat-governed-evidence.json"
    assert out.is_file()


def test_structured_project_scope_from_semantic_model():
    from uuid import uuid4

    from app.core.config import Settings
    from app.core.models import AskDataRequest, ChatContextSource
    from app.db.platform_models import Base, SemanticModelRow, ProjectRow, WorkspaceRow
    from app.db.platform_engine import get_platform_engine, get_session_factory
    from app.projects.scope import resolve_structured_project_scope
    from pydantic import SecretStr

    url = f"sqlite+pysqlite:///{Path('/tmp/cai-scope-test.db')}"
    if Path("/tmp/cai-scope-test.db").exists():
        Path("/tmp/cai-scope-test.db").unlink()
    engine = get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    ws_id = uuid4()
    proj_id = uuid4()
    model_id = uuid4()
    with factory() as session:
        session.add(WorkspaceRow(id=ws_id, slug="default", name="Default"))
        session.flush()
        session.add(
            ProjectRow(
                id=proj_id,
                workspace_id=ws_id,
                slug="banking",
                name="Banking",
                ossie_root_path="ossie/banking",
                status="active",
            )
        )
        session.flush()
        session.add(
            SemanticModelRow(
                id=model_id,
                workspace_id=ws_id,
                project_id=proj_id,
                key="retail_banking_analytics",
                name="Retail Banking Analytics",
            )
        )
        session.commit()
        settings = Settings.model_construct(
            database_url=url,
            qwen_api_key=SecretStr("x"),
            qwen_base_url="http://x",
            qwen_model="m",
        )
        req = AskDataRequest(
            session_id="s",
            question="total?",
            provider="qwen",
            model="m",
            context_sources=[
                ChatContextSource(type="semantic_model", id=str(model_id), name="Retail Banking Analytics")
            ],
        )
        project = resolve_structured_project_scope(session, settings, req)
        assert project is not None
        assert project.id == proj_id


def test_structured_project_scope_from_semantic_metric():
    from uuid import uuid4

    from app.core.config import Settings
    from app.core.models import AskDataRequest, ChatContextSource
    from app.db.platform_models import (
        Base,
        ProjectRow,
        SemanticMetricRow,
        SemanticModelRow,
        SemanticVersionRow,
        WorkspaceRow,
    )
    from app.db.platform_engine import get_platform_engine, get_session_factory
    from app.projects.scope import resolve_structured_project_scope
    from pydantic import SecretStr

    url = f"sqlite+pysqlite:///{Path('/tmp/cai-scope-metric-test.db')}"
    db_path = Path("/tmp/cai-scope-metric-test.db")
    if db_path.exists():
        db_path.unlink()
    engine = get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    ws_id = uuid4()
    proj_id = uuid4()
    model_id = uuid4()
    version_id = uuid4()
    metric_id = uuid4()
    with factory() as session:
        session.add(WorkspaceRow(id=ws_id, slug="default", name="Default"))
        session.flush()
        session.add(
            ProjectRow(
                id=proj_id,
                workspace_id=ws_id,
                slug="banking",
                name="Banking",
                ossie_root_path="ossie/banking",
                status="active",
            )
        )
        session.flush()
        session.add(
            SemanticModelRow(
                id=model_id,
                workspace_id=ws_id,
                project_id=proj_id,
                key="retail_banking_analytics",
                name="Retail Banking Analytics",
            )
        )
        session.flush()
        session.add(
            SemanticVersionRow(
                id=version_id,
                semantic_model_id=model_id,
                version_number=1,
                status="ACTIVE",
            )
        )
        session.flush()
        session.add(
            SemanticMetricRow(
                id=metric_id,
                semantic_version_id=version_id,
                key="total_transaction_amount",
                name="Total Transaction Amount",
                expression="SUM(amount)",
                source_entity_key="transactions",
            )
        )
        session.commit()
        settings = Settings.model_construct(
            database_url=url,
            qwen_api_key=SecretStr("x"),
            qwen_base_url="http://x",
            qwen_model="m",
        )
        req = AskDataRequest(
            session_id="s",
            question="total?",
            provider="qwen",
            model="m",
            context_sources=[
                ChatContextSource(
                    type="semantic_metric",
                    id=str(metric_id),
                    name="Total Transaction Amount",
                )
            ],
        )
        project = resolve_structured_project_scope(session, settings, req)
        assert project is not None
        assert project.id == proj_id
