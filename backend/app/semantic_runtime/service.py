from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.platform_models import (
    SemanticModelRow,
    SemanticRuntimeDeploymentRow,
    SemanticRuntimeEventRow,
    SemanticRuntimeStateRow,
    SemanticVersionRow,
)
from app.semantic_runtime.loader import SemanticRuntimeLoader
from app.semantic_registry.governance_types import READINESS_NOT_READY, READINESS_READY, READINESS_WITH_WARNINGS
from app.semantic_registry.governance_pipeline import SemanticGovernancePipeline
from app.semantic_runtime.storage import GENERATOR_VERSION, logical_artifact_uri, write_deployment_artifact


class SemanticRuntimeError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SemanticRuntimeService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    def _log_event(self, deployment_id: uuid.UUID, event_type: str, detail: dict | None = None) -> None:
        self._session.add(
            SemanticRuntimeEventRow(
                deployment_id=deployment_id,
                event_type=event_type,
                detail=detail or {},
            )
        )

    def _get_model(self, model_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> SemanticModelRow:
        row = self._session.get(SemanticModelRow, model_id)
        if not row or row.workspace_id != workspace_id or row.project_id != project_id:
            raise SemanticRuntimeError("not_found", "Semantic model not found", 404)
        return row

    def _get_version(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> SemanticVersionRow:
        version = self._session.get(SemanticVersionRow, version_id)
        if not version:
            raise SemanticRuntimeError("not_found", "Semantic version not found", 404)
        self._get_model(version.semantic_model_id, workspace_id=workspace_id, project_id=project_id)
        return version

    def _ensure_state(self, model_id: uuid.UUID) -> SemanticRuntimeStateRow:
        state = self._session.get(SemanticRuntimeStateRow, model_id)
        if not state:
            state = SemanticRuntimeStateRow(semantic_model_id=model_id)
            self._session.add(state)
            self._session.flush()
        return state

    def _assert_no_active_activation(self, model_id: uuid.UUID) -> None:
        running = self._session.execute(
            select(SemanticRuntimeDeploymentRow).where(
                SemanticRuntimeDeploymentRow.semantic_model_id == model_id,
                SemanticRuntimeDeploymentRow.status == "ACTIVATING",
            )
        ).scalar_one_or_none()
        if running:
            raise SemanticRuntimeError("activation_in_progress", "Another activation is in progress", 409)

    def stage_version(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        created_by: str | None = None,
    ) -> SemanticRuntimeDeploymentRow:
        version = self._get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        if version.status != "ACTIVE":
            raise SemanticRuntimeError("invalid_state", "Only registry ACTIVE versions can be staged for runtime", 409)
        readiness = version.activation_readiness
        if readiness == READINESS_NOT_READY or not readiness:
            raise SemanticRuntimeError("not_ready", "Semantic version is NOT_READY for runtime activation", 422)

        model = self._get_model(version.semantic_model_id, workspace_id=workspace_id, project_id=project_id)
        deployment_id = uuid.uuid4()
        uri, checksum, manifest, _root = write_deployment_artifact(
            self._session,
            settings=self._settings,
            workspace_id=workspace_id,
            project_id=project_id,
            model_key=model.key,
            deployment_id=deployment_id,
            version_id=version_id,
            version_number=version.version_number,
            source_validation_run_id=version.last_validation_run_id,
        )
        row = SemanticRuntimeDeploymentRow(
            id=deployment_id,
            workspace_id=workspace_id,
            project_id=project_id,
            semantic_model_id=model.id,
            semantic_version_id=version_id,
            runtime_adapter="ossie",
            artifact_uri=uri,
            artifact_checksum=checksum,
            status="STAGED",
            source_validation_run_id=version.last_validation_run_id,
            registry_version_number=version.version_number,
            generator_version=GENERATOR_VERSION,
            created_by=created_by,
            manifest=manifest,
        )
        self._session.add(row)
        self._log_event(deployment_id, "GENERATED", {"checksum": checksum})
        self._session.flush()
        return row

    def validate_deployment(
        self,
        deployment_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        deployment = self._get_deployment(deployment_id, workspace_id=workspace_id, project_id=project_id)
        deployment.status = "VALIDATING"
        self._log_event(deployment_id, "VALIDATED", {"phase": "start"})
        ok, message = self._validate_staged_files(deployment)
        if not ok:
            deployment.status = "FAILED"
            deployment.error_summary = message
            deployment.completed_at = datetime.now(timezone.utc)
            self._log_event(deployment_id, "FAILED", {"message": message})
            self._session.flush()
            return {"valid": False, "message": message}
        deployment.status = "READY"
        self._log_event(deployment_id, "VALIDATED", {"phase": "complete"})
        self._session.flush()
        return {"valid": True, "message": "Staged artifact validated"}

    def smoke_deployment(
        self,
        deployment_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        deployment = self._get_deployment(deployment_id, workspace_id=workspace_id, project_id=project_id)
        project_dir = self._deployment_project_dir(deployment)
        ok, message = SemanticRuntimeLoader.smoke_test_project_dir(project_dir)
        if ok:
            self._log_event(deployment_id, "SMOKE_PASSED", {})
        else:
            self._log_event(deployment_id, "FAILED", {"smoke": message})
        return {"passed": ok, "message": message}

    def activate_deployment(
        self,
        deployment_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        dry_run: bool = False,
        created_by: str | None = None,
    ) -> dict:
        deployment = self._get_deployment(deployment_id, workspace_id=workspace_id, project_id=project_id)
        model = self._get_model(deployment.semantic_model_id, workspace_id=workspace_id, project_id=project_id)
        version = self._get_version(deployment.semantic_version_id, workspace_id=workspace_id, project_id=project_id)

        if version.activation_readiness == READINESS_NOT_READY:
            raise SemanticRuntimeError("not_ready", "Registry version NOT_READY", 422)

        self._assert_no_active_activation(model.id)
        state = self._session.get(SemanticRuntimeStateRow, model.id, with_for_update=True)
        if state is None:
            state = self._ensure_state(model.id)
            self._session.flush()
            state = self._session.get(SemanticRuntimeStateRow, model.id, with_for_update=True)

        validation = self.validate_deployment(deployment_id, workspace_id=workspace_id, project_id=project_id)
        if not validation["valid"]:
            raise SemanticRuntimeError("validation_failed", validation["message"], 422)

        smoke = self.smoke_deployment(deployment_id, workspace_id=workspace_id, project_id=project_id)
        if not smoke["passed"]:
            raise SemanticRuntimeError("smoke_failed", smoke["message"], 422)

        if dry_run:
            return {
                "dry_run": True,
                "result": "READY_TO_ACTIVATE",
                "deployment_id": str(deployment_id),
                "artifact_checksum": deployment.artifact_checksum,
            }

        if state.active_deployment_id == deployment_id:
            return {"result": "ALREADY_ACTIVE", "deployment_id": str(deployment_id)}

        prev_deployment_id = state.active_deployment_id
        deployment.status = "ACTIVATING"
        deployment.previous_deployment_id = prev_deployment_id
        self._log_event(deployment_id, "ACTIVATED", {"previous": str(prev_deployment_id) if prev_deployment_id else None})
        self._session.flush()

        project_dir = self._deployment_project_dir(deployment)
        if not self._verify_checksum(deployment, project_dir):
            deployment.status = "FAILED"
            deployment.error_summary = "Checksum mismatch"
            deployment.completed_at = datetime.now(timezone.utc)
            self._session.flush()
            raise SemanticRuntimeError("checksum_mismatch", "Artifact checksum mismatch", 422)

        loader = SemanticRuntimeLoader.get(self._settings)
        try:
            new_bundle = loader._bundle_from_deployment(deployment, model.key)  # noqa: SLF001
        except Exception as exc:
            deployment.status = "FAILED"
            deployment.error_summary = str(exc)
            self._log_event(deployment_id, "FAILED", {"load": str(exc)})
            self._session.flush()
            raise SemanticRuntimeError("load_failed", str(exc), 422) from exc

        prev_bundle = loader.get_bundle()
        loader.swap_bundle(new_bundle)

        healthy, health_msg = SemanticRuntimeLoader.smoke_test_project_dir(project_dir)
        if not healthy:
            loader.swap_bundle(prev_bundle)
            deployment.status = "FAILED"
            deployment.error_summary = health_msg
            deployment.health_status = "failed"
            deployment.completed_at = datetime.now(timezone.utc)
            self._log_event(deployment_id, "FAILED", {"health": health_msg})
            self._log_event(deployment_id, "ROLLBACK_STARTED", {"automatic": True})
            if prev_deployment_id:
                self._log_event(prev_deployment_id, "ROLLED_BACK", {"reason": "post_activation_health_failed"})
            self._session.flush()
            raise SemanticRuntimeError("health_failed", health_msg, 422)

        if prev_deployment_id:
            prev = self._session.get(SemanticRuntimeDeploymentRow, prev_deployment_id)
            if prev and prev.status == "ACTIVE":
                prev.status = "SUPERSEDED"
                prev.completed_at = datetime.now(timezone.utc)

        state.previous_deployment_id = prev_deployment_id
        state.active_deployment_id = deployment.id
        state.updated_at = datetime.now(timezone.utc)

        deployment.status = "ACTIVE"
        deployment.activated_at = datetime.now(timezone.utc)
        deployment.completed_at = deployment.activated_at
        deployment.health_status = "healthy"
        self._log_event(deployment_id, "HEALTH_PASSED", {})
        self._session.flush()
        return {
            "result": "ACTIVATED",
            "deployment_id": str(deployment_id),
            "registry_version": deployment.registry_version_number,
            "runtime_active_version": deployment.registry_version_number,
        }

    def rollback_deployment(
        self,
        deployment_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        target = self._get_deployment(deployment_id, workspace_id=workspace_id, project_id=project_id)
        if target.status not in {"ACTIVE", "SUPERSEDED"}:
            raise SemanticRuntimeError("invalid_state", "Rollback target must be a previously active deployment", 409)

        model = self._get_model(target.semantic_model_id, workspace_id=workspace_id, project_id=project_id)
        state = self._ensure_state(model.id)
        current_id = state.active_deployment_id

        project_dir = self._deployment_project_dir(target)
        if not self._verify_checksum(target, project_dir):
            raise SemanticRuntimeError("checksum_mismatch", "Target artifact checksum invalid", 422)

        loader = SemanticRuntimeLoader.get(self._settings)
        bundle = loader._bundle_from_deployment(target, model.key)  # noqa: SLF001
        loader.swap_bundle(bundle)

        ok, msg = SemanticRuntimeLoader.smoke_test_project_dir(project_dir)
        if not ok:
            raise SemanticRuntimeError("health_failed", msg, 422)

        if current_id and current_id != target.id:
            current = self._session.get(SemanticRuntimeDeploymentRow, current_id)
            if current:
                current.status = "SUPERSEDED"
                current.completed_at = datetime.now(timezone.utc)

        target.status = "ACTIVE"
        target.activated_at = datetime.now(timezone.utc)
        target.health_status = "healthy"
        state.previous_deployment_id = current_id
        state.active_deployment_id = target.id
        state.updated_at = datetime.now(timezone.utc)
        self._log_event(deployment_id, "ROLLED_BACK", {"from": str(current_id) if current_id else None})
        self._session.flush()
        return {"result": "ROLLED_BACK", "deployment_id": str(deployment_id)}

    def runtime_status(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        model_key: str | None = None,
    ) -> dict:
        model_key = model_key or self._settings.semantic_default_model_key
        model = self._session.execute(
            select(SemanticModelRow).where(
                SemanticModelRow.workspace_id == workspace_id,
                SemanticModelRow.project_id == project_id,
                SemanticModelRow.key == model_key,
            )
        ).scalar_one_or_none()
        if not model:
            return {"runtime_status": "legacy_fallback", "registry_active_version": None, "runtime_active_version": None}

        registry_version = None
        if model.active_version_id:
            active_v = self._session.get(SemanticVersionRow, model.active_version_id)
            if active_v:
                registry_version = active_v.version_number

        state = self._session.get(SemanticRuntimeStateRow, model.id)
        runtime_version = None
        deployment_meta = None
        if state and state.active_deployment_id:
            dep = self._session.get(SemanticRuntimeDeploymentRow, state.active_deployment_id)
            if dep and dep.status == "ACTIVE":
                runtime_version = dep.registry_version_number
                deployment_meta = {
                    "deployment_id": str(dep.id),
                    "artifact_checksum": dep.artifact_checksum,
                    "activated_at": dep.activated_at,
                    "adapter": dep.runtime_adapter,
                    "health": dep.health_status,
                }

        loader = SemanticRuntimeLoader.get()
        bundle = loader.get_bundle()
        health = "healthy"
        if bundle.mode == "legacy":
            health = "legacy_fallback"
        elif registry_version and runtime_version and registry_version != runtime_version:
            health = "healthy"

        return {
            "semantic_model_key": model.key,
            "registry_active_version": registry_version,
            "runtime_active_version": runtime_version,
            "runtime_status": health,
            "deployment": deployment_meta,
            "loader_mode": bundle.mode,
        }

    def list_deployments(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        model_key: str | None = None,
        limit: int = 50,
    ) -> list[SemanticRuntimeDeploymentRow]:
        model_key = model_key or self._settings.semantic_default_model_key
        model = self._session.execute(
            select(SemanticModelRow).where(
                SemanticModelRow.workspace_id == workspace_id,
                SemanticModelRow.project_id == project_id,
                SemanticModelRow.key == model_key,
            )
        ).scalar_one_or_none()
        if not model:
            return []
        return list(
            self._session.execute(
                select(SemanticRuntimeDeploymentRow)
                .where(SemanticRuntimeDeploymentRow.semantic_model_id == model.id)
                .order_by(SemanticRuntimeDeploymentRow.created_at.desc())
                .limit(limit)
            ).scalars().all()
        )

    def get_deployment_detail(
        self,
        deployment_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        dep = self._get_deployment(deployment_id, workspace_id=workspace_id, project_id=project_id)
        events = list(
            self._session.execute(
                select(SemanticRuntimeEventRow)
                .where(SemanticRuntimeEventRow.deployment_id == deployment_id)
                .order_by(SemanticRuntimeEventRow.created_at)
            ).scalars().all()
        )
        return {"deployment": self._deployment_dict(dep), "events": [self._event_dict(e) for e in events]}

    def _get_deployment(
        self,
        deployment_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> SemanticRuntimeDeploymentRow:
        dep = self._session.get(SemanticRuntimeDeploymentRow, deployment_id)
        if not dep or dep.workspace_id != workspace_id or dep.project_id != project_id:
            raise SemanticRuntimeError("not_found", "Deployment not found", 404)
        return dep

    def _deployment_project_dir(self, deployment: SemanticRuntimeDeploymentRow) -> Path:
        from app.semantic_runtime.storage import deployment_dir

        model = self._session.get(SemanticModelRow, deployment.semantic_model_id)
        assert model
        return deployment_dir(
            self._settings,
            workspace_id=deployment.workspace_id,
            project_id=deployment.project_id,
            model_key=model.key,
            deployment_id=deployment.id,
        )

    def _verify_checksum(self, deployment: SemanticRuntimeDeploymentRow, project_dir: Path) -> bool:
        core = project_dir / "ossie" / "tempo_core.ossie.yaml"
        if not core.is_file():
            return False
        checksum = hashlib.sha256(core.read_bytes()).hexdigest()
        return checksum == deployment.artifact_checksum

    def _validate_staged_files(self, deployment: SemanticRuntimeDeploymentRow) -> tuple[bool, str]:
        project_dir = self._deployment_project_dir(deployment)
        core = project_dir / "ossie" / "tempo_core.ossie.yaml"
        if not core.is_file():
            return False, "Missing tempo_core.ossie.yaml in staged deployment"
        if not self._verify_checksum(deployment, project_dir):
            return False, "Artifact checksum mismatch"
        try:
            parsed = yaml.safe_load(core.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            return False, f"Invalid YAML: {exc}"
        if not isinstance(parsed, dict) or "datasets" not in parsed or "metrics" not in parsed:
            return False, "OSSIE artifact missing required sections"
        return True, "ok"

    @staticmethod
    def _deployment_dict(dep: SemanticRuntimeDeploymentRow) -> dict:
        return {
            "id": str(dep.id),
            "semantic_model_id": str(dep.semantic_model_id),
            "semantic_version_id": str(dep.semantic_version_id),
            "registry_version_number": dep.registry_version_number,
            "status": dep.status,
            "artifact_uri": dep.artifact_uri,
            "artifact_checksum": dep.artifact_checksum,
            "runtime_adapter": dep.runtime_adapter,
            "health_status": dep.health_status,
            "error_summary": dep.error_summary,
            "created_at": dep.created_at,
            "activated_at": dep.activated_at,
            "created_by": dep.created_by,
        }

    @staticmethod
    def _event_dict(event: SemanticRuntimeEventRow) -> dict:
        return {
            "id": str(event.id),
            "event_type": event.event_type,
            "detail": event.detail,
            "created_at": event.created_at,
        }
