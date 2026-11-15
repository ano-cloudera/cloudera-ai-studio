"""A choice saved in Settings, Ask Data, Advanced must come back: the workspace's own settings are read with the id an endpoint passes."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.platform_models import Base, WorkspaceRow
from app.workspace.ask_data_settings import AskDataSettings, write_ask_data_settings
from app.workspace.presentation_config_resolver import load_presentation_tier_config


def _factory(**presentation):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[WorkspaceRow.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        row = WorkspaceRow(slug="default", name="Default", settings_json=write_ask_data_settings({}, AskDataSettings.model_validate({"presentation": presentation})))
        session.add(row)
        session.commit()
        return factory, row.id


def test_a_saved_presentation_choice_is_read_back_whether_the_id_is_a_uuid_or_text() -> None:
    factory, workspace_id = _factory(tier1_show_narrative=False, panel_auto_open="never")
    for key in (workspace_id, str(workspace_id)):  # the endpoint passes text
        config = load_presentation_tier_config(get_settings(), session_factory=factory, workspace_id=key)
        assert config.tier1_show_narrative is False and config.panel_auto_open == "never"


def test_without_a_saved_choice_or_a_workspace_the_deployment_default_applies() -> None:
    factory, workspace_id = _factory()
    assert load_presentation_tier_config(get_settings(), session_factory=factory, workspace_id=str(workspace_id)).tier1_show_narrative is True
    assert load_presentation_tier_config(get_settings(), session_factory=None, workspace_id=None).tier1_show_narrative is True
    assert load_presentation_tier_config(get_settings(), session_factory=factory, workspace_id="not-a-uuid").tier1_show_narrative is True  # no crash
