from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.platform_models import SemanticModelRow, SemanticRuntimeDeploymentRow, SemanticRuntimeStateRow
from app.projects.resolver import resolve_ossie_project_dir
from app.semantic.context import SemanticContextService
from app.semantic.registry import TempoOssieRegistry
from app.semantic_runtime.storage import deployment_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeContextBundle:
    context: SemanticContextService
    mode: str  # runtime | legacy
    deployment_id: uuid.UUID | None
    semantic_version_id: uuid.UUID | None
    registry_version_number: int | None
    artifact_checksum: str | None
    health: str


class SemanticRuntimeLoader:
    """Controlled OSSIE runtime loader with legacy fallback."""

    _instance: SemanticRuntimeLoader | None = None
    _lock = threading.RLock()

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._bundle: RuntimeContextBundle | None = None

    @classmethod
    def get(cls, settings: Settings | None = None) -> SemanticRuntimeLoader:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SemanticRuntimeLoader(settings)
            elif settings is not None:
                cls._instance.settings = settings
            return cls._instance

    def _legacy_bundle(self) -> RuntimeContextBundle:
        project_dir = resolve_ossie_project_dir(self.settings)
        ctx = SemanticContextService(project_dir)
        return RuntimeContextBundle(
            context=ctx,
            mode="legacy",
            deployment_id=None,
            semantic_version_id=None,
            registry_version_number=None,
            artifact_checksum=None,
            health="legacy_fallback",
        )

    def _bundle_from_deployment(self, deployment: SemanticRuntimeDeploymentRow, model_key: str) -> RuntimeContextBundle:
        root = deployment_dir(
            self.settings,
            workspace_id=deployment.workspace_id,
            project_id=deployment.project_id,
            model_key=model_key,
            deployment_id=deployment.id,
        )
        ctx = SemanticContextService(root, validate_profile=False)
        return RuntimeContextBundle(
            context=ctx,
            mode="runtime",
            deployment_id=deployment.id,
            semantic_version_id=deployment.semantic_version_id,
            registry_version_number=deployment.registry_version_number,
            artifact_checksum=deployment.artifact_checksum,
            health=deployment.health_status or "healthy",
        )

    def _bundle_for_model(
        self,
        session: Session,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        model: SemanticModelRow,
    ) -> RuntimeContextBundle | None:
        state = session.get(SemanticRuntimeStateRow, model.id)
        if not state or not state.active_deployment_id:
            return None

        deployment = session.get(SemanticRuntimeDeploymentRow, state.active_deployment_id)
        if not deployment or deployment.status != "ACTIVE":
            return None

        try:
            return self._bundle_from_deployment(deployment, model.key)
        except Exception as exc:
            logger.warning("runtime deployment load failed: %s — trying previous", exc)
            if state.previous_deployment_id:
                prev = session.get(SemanticRuntimeDeploymentRow, state.previous_deployment_id)
                if prev and prev.status in {"ACTIVE", "SUPERSEDED"}:
                    try:
                        return self._bundle_from_deployment(prev, model.key)
                    except Exception:
                        pass
            return None

    def load_from_session(
        self,
        session: Session,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        model_key: str | None = None,
    ) -> RuntimeContextBundle:
        model_key = model_key or self.settings.semantic_default_model_key
        model = session.execute(
            select(SemanticModelRow).where(
                SemanticModelRow.workspace_id == workspace_id,
                SemanticModelRow.project_id == project_id,
                SemanticModelRow.key == model_key,
            )
        ).scalar_one_or_none()
        if model is not None:
            bundle = self._bundle_for_model(
                session, workspace_id=workspace_id, project_id=project_id, model=model
            )
            if bundle is not None:
                return bundle
            logger.warning("semantic model %s has no active runtime deployment", model_key)
            return self._legacy_bundle()

        return self._legacy_bundle()

    def load_first_active_runtime(
        self,
        session: Session,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> RuntimeContextBundle | None:
        """Prefer any published semantic runtime in the project over legacy Tempo OSSIE."""
        models = session.execute(
            select(SemanticModelRow).where(
                SemanticModelRow.workspace_id == workspace_id,
                SemanticModelRow.project_id == project_id,
            )
        ).scalars()
        for model in models:
            bundle = self._bundle_for_model(
                session,
                workspace_id=workspace_id,
                project_id=project_id,
                model=model,
            )
            if bundle is not None:
                return bundle
        return None

    def refresh(self, session: Session, *, workspace_id: uuid.UUID, project_id: uuid.UUID, model_key: str | None = None) -> RuntimeContextBundle:
        with self._lock:
            bundle = self.load_from_session(
                session,
                workspace_id=workspace_id,
                project_id=project_id,
                model_key=model_key,
            )
            self._bundle = bundle
            return bundle

    def get_bundle(self) -> RuntimeContextBundle:
        with self._lock:
            if self._bundle is None:
                return self._legacy_bundle()
            return self._bundle

    def swap_bundle(self, bundle: RuntimeContextBundle) -> None:
        with self._lock:
            self._bundle = bundle

    @staticmethod
    def smoke_test_project_dir(project_dir: Path) -> tuple[bool, str]:
        core = project_dir / "ossie" / "tempo_core.ossie.yaml"
        if not core.is_file():
            return False, "Missing tempo_core.ossie.yaml"
        try:
            registry = TempoOssieRegistry(project_dir)
            if not registry.metrics:
                return False, "No metrics in staged OSSIE artifact"
            if not registry.datasets:
                return False, "No datasets in staged OSSIE artifact"
            return True, "ok"
        except ValueError:
            try:
                parsed = yaml.safe_load(core.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                return False, f"Invalid YAML: {exc}"
            if isinstance(parsed, dict) and parsed.get("metrics") and parsed.get("datasets"):
                return True, "ok (registry artifact; full TEMPO profile not required)"
            return False, "OSSIE artifact failed load and is not a minimal valid document"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
