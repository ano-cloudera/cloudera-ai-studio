from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_platform_engine, get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.workspace.feature_overrides import FeatureOverrides, read_feature_overrides, write_feature_overrides
from tests.semantic_schema_helpers import ensure_s3_governance_schema


def test_only_the_switchable_features_are_accepted() -> None:
    assert FeatureOverrides(overrides={"skills": True, "usage": False, "semanticLayer": False}).overrides["usage"] is False
    for locked in ("askData", "settings", "aiModelRegistry"):
        with pytest.raises(ValidationError, match="cannot be switched off"):
            FeatureOverrides(overrides={locked: False})
    with pytest.raises(ValidationError, match="Unknown features"):
        FeatureOverrides(overrides={"telepathy": True})
    with pytest.raises(ValidationError):
        FeatureOverrides(overrides={"skills": "maybe"})


def test_the_overrides_are_stored_beside_the_other_workspace_settings() -> None:
    stored = write_feature_overrides({"ask_data": {"keep": 1}}, FeatureOverrides(overrides={"skills": True}))
    assert stored["ask_data"] == {"keep": 1}
    assert read_feature_overrides(stored).overrides == {"skills": True}
    assert read_feature_overrides(None).overrides == {} and read_feature_overrides({"feature_overrides": "junk"}).overrides == {}


@pytest.fixture()
def client(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'features.db'}"
    engine = get_platform_engine(url)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    with get_session_factory(url)() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
    settings = Settings(_env_file=None, state_store="sqlite", database_url=url, qwen_base_url="https://qwen", qwen_api_key=SecretStr("token"), qwen_model="qwen-model")
    return TestClient(create_app(settings))


def test_the_api_stores_resets_and_refuses(client) -> None:
    first = client.get("/api/v1/features/overrides").json()
    assert first["overrides"] == {} and "skills" in first["switchable"] and "askData" in first["locked"]
    saved = client.put("/api/v1/features/overrides", json={"overrides": {"skills": True, "usage": False}})
    assert saved.status_code == 200 and saved.json()["overrides"] == {"skills": True, "usage": False}
    assert client.get("/api/v1/features/overrides").json()["overrides"] == {"skills": True, "usage": False}
    assert client.put("/api/v1/features/overrides", json={"overrides": {"settings": False}}).status_code == 422
    assert client.put("/api/v1/features/overrides", json={"overrides": {"nope": True}}).status_code == 422
    assert client.get("/api/v1/features/overrides").json()["overrides"] == {"skills": True, "usage": False}  # a refused change stores nothing
    assert client.put("/api/v1/features/overrides", json={"overrides": {}}).json()["overrides"] == {}  # reset


def test_switching_features_leaves_the_ask_data_settings_alone(client) -> None:
    settings = client.get("/api/v1/ask-data/settings").json()["settings"]
    client.put("/api/v1/ask-data/settings", json={**settings, "starter_questions_caption": "Keep me"})
    client.put("/api/v1/features/overrides", json={"overrides": {"prompts": False}})
    assert client.get("/api/v1/ask-data/settings").json()["settings"]["starter_questions_caption"] == "Keep me"
