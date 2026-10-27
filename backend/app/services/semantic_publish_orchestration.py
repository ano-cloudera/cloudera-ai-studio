"""Orchestrates validate → registry publish → runtime stage → activate for Semantic Layer V2 UX."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.semantic_registry.governance_types import READINESS_NOT_READY
from app.semantic_registry.registry_errors import SemanticRegistryError
from app.semantic_registry.validation import SemanticValidationService
from app.semantic_runtime.service import SemanticRuntimeError, SemanticRuntimeService
from app.services.semantic_registry_service import SemanticRegistryService

logger = logging.getLogger(__name__)


@dataclass
class PublishIssue:
    object_type: str
    object_id: str | None
    object_name: str | None
    code: str
    message: str

    def to_dict(self) -> dict:
        return {
            "object_type": self.object_type,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "code": self.code,
            "message": self.message,
        }


class SemanticPublishOrchestrationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._registry = SemanticRegistryService(session)
        self._runtime = SemanticRuntimeService(session)

    def publish_to_ask_data(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        created_by: str | None = None,
    ) -> dict:
        model = self._registry.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        version, registry_already_active = self._resolve_publish_target(
            model,
            model_id,
            version_id,
            workspace_id=workspace_id,
            project_id=project_id,
        )

        logger.info(
            "semantic_publish_to_ask_data started model=%s version=%s registry_active=%s project=%s",
            model.key,
            version.id,
            registry_already_active,
            project_id,
        )

        validation = SemanticValidationService(self._session).validate_version(
            version.id,
            mode="full",
            created_by=created_by,
        )
        if not validation.valid or validation.summary.readiness == READINESS_NOT_READY:
            issues = self._issues_from_validation(validation)
            logger.info("semantic_publish_to_ask_data validation_failed version=%s issues=%s", version.id, len(issues))
            return {
                "status": "needs_attention",
                "model_id": str(model_id),
                "version_id": str(version.id),
                "issues": [i.to_dict() for i in issues],
            }

        if registry_already_active:
            published = version
        else:
            try:
                published = self._registry.publish_version(
                    version.id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    artifact_preview=True,
                )
            except SemanticRegistryError as exc:
                if exc.code == "validation_failed":
                    return {
                        "status": "needs_attention",
                        "model_id": str(model_id),
                        "version_id": str(version.id),
                        "issues": [{"object_type": "model", "object_id": str(model_id), "object_name": model.name, "code": exc.code, "message": exc.message}],
                    }
                raise

        deployment = self._runtime.stage_version(
            published.id,
            workspace_id=workspace_id,
            project_id=project_id,
            created_by=created_by,
        )
        try:
            activation = self._runtime.activate_deployment(
                deployment.id,
                workspace_id=workspace_id,
                project_id=project_id,
                created_by=created_by,
            )
        except SemanticRuntimeError as exc:
            logger.warning(
                "semantic_publish_to_ask_data activation_failed deployment=%s code=%s",
                deployment.id,
                exc.code,
            )
            return {
                "status": "activation_failed",
                "model_id": str(model_id),
                "version_id": str(published.id),
                "runtime_deployment_id": str(deployment.id),
                "message": exc.message,
                "code": exc.code,
                "checks": [],
            }

        logger.info(
            "semantic_publish_to_ask_data success model=%s version=%s deployment=%s",
            model.key,
            published.version_number,
            deployment.id,
        )
        return {
            "status": "published",
            "model_id": str(model_id),
            "model_key": model.key,
            "version_id": str(published.id),
            "version_number": published.version_number,
            "runtime_deployment_id": str(deployment.id),
            "activation": activation,
            "checks": [],
        }

    def _resolve_publish_target(
        self,
        model,
        model_id: uuid.UUID,
        version_id: uuid.UUID | None,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ):
        """Return (version, registry_already_active). Prefer DRAFT; else ACTIVE registry when no draft."""

        def _as_target(version):
            if version.semantic_model_id != model_id:
                raise SemanticRegistryError("invalid_state", "Version does not belong to model", 400)
            if version.status == "DRAFT":
                return version, False
            if version.status == "ACTIVE":
                return version, True
            raise SemanticRegistryError("invalid_state", "Publish requires a DRAFT or ACTIVE registry version", 409)

        if version_id is not None:
            version = self._registry.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
            return _as_target(version)

        for row in self._registry.list_versions(model_id, workspace_id=workspace_id, project_id=project_id):
            if row.status == "DRAFT":
                return row, False

        active_id = getattr(model, "active_version_id", None)
        if active_id:
            active = self._registry.get_version(active_id, workspace_id=workspace_id, project_id=project_id)
            if active.status == "ACTIVE":
                return active, True

        raise SemanticRegistryError("not_found", "No DRAFT version available to publish", 404)

    @staticmethod
    def _issues_from_validation(validation) -> list[PublishIssue]:
        issues: list[PublishIssue] = []
        for item in list(validation.errors) + list(getattr(validation, "warnings", []) or []):
            if getattr(item, "severity", "ERROR") == "INFO":
                continue
            issues.append(
                PublishIssue(
                    object_type=item.object_type or item.category or "model",
                    object_id=None,
                    object_name=item.object_key,
                    code=item.code,
                    message=item.message,
                )
            )
        return issues
