"""Resolve workspace/project scope for Ask Data structured context."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.models import AskDataRequest
from app.db.platform_models import SemanticEntityRow, SemanticMetricRow, SemanticModelRow, SemanticTermRow
from app.projects.resolver import load_default_project
from app.projects.types import ProjectRecord


def resolve_structured_project_scope(
    session: Session,
    settings: Settings,
    request: AskDataRequest,
) -> ProjectRecord | None:
    """Prefer the project that owns explicit structured context (semantic model/entity/table)."""
    for source in request.context_sources or []:
        try:
            if source.type == "semantic_model":
                model = session.get(SemanticModelRow, uuid.UUID(source.id))
                if model is not None:
                    return _project_record(session, model.project_id, settings)
            if source.type == "semantic_entity":
                entity = session.get(SemanticEntityRow, uuid.UUID(source.id))
                if entity is not None:
                    return _project_from_version(session, entity.semantic_version_id, settings)
            if source.type == "semantic_metric":
                try:
                    metric_id = uuid.UUID(source.id)
                except ValueError:
                    continue
                metric = session.get(SemanticMetricRow, metric_id)
                if metric is not None:
                    scoped = _project_from_version(session, metric.semantic_version_id, settings)
                    if scoped is not None:
                        return scoped
            if source.type == "semantic_term":
                term = session.get(SemanticTermRow, uuid.UUID(source.id))
                if term is not None:
                    scoped = _project_from_version(session, term.semantic_version_id, settings)
                    if scoped is not None:
                        return scoped
        except ValueError:
            continue
    return load_default_project(settings)


def _project_from_version(session: Session, version_id: uuid.UUID, settings: Settings) -> ProjectRecord | None:
    from app.db.platform_models import SemanticVersionRow

    version = session.get(SemanticVersionRow, version_id)
    if version is None:
        return None
    model = session.get(SemanticModelRow, version.semantic_model_id)
    if model is None:
        return None
    return _project_record(session, model.project_id, settings)


def _project_record(session: Session, project_id: uuid.UUID, settings: Settings) -> ProjectRecord | None:
    from app.db.platform_models import ProjectRow

    project = session.get(ProjectRow, project_id)
    if project is None or project.status != "active":
        return load_default_project(settings)
    return ProjectRecord(
        id=project.id,
        workspace_id=project.workspace_id,
        slug=project.slug,
        name=project.name,
        ossie_root_path=project.ossie_root_path,
        status=project.status,
        default_connector_id=project.default_connector_id,
    )


def load_project_for_semantic_model_key(
    session: Session,
    settings: Settings,
    model_key: str,
) -> ProjectRecord | None:
    model = session.scalar(select(SemanticModelRow).where(SemanticModelRow.key == model_key))
    if model is None:
        return load_default_project(settings)
    return _project_record(session, model.project_id, settings)
