from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.documents.bulk_schemas import BulkDeleteResponse, BulkDeletedItem, BulkFailedItem
from app.semantic_registry.registry_errors import SemanticRegistryError
from app.services.semantic_registry_service import SemanticRegistryService


class SemanticBulkDeleteService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._registry = SemanticRegistryService(session)

    def _max_items(self) -> int:
        return self._settings.bulk_delete_max_items

    def delete_entities(
        self, version_id: uuid.UUID, ids: list[str], *, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> BulkDeleteResponse:
        return self._delete(version_id, ids, workspace_id=workspace_id, project_id=project_id, kind="entity")

    def delete_metrics(
        self, version_id: uuid.UUID, ids: list[str], *, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> BulkDeleteResponse:
        return self._delete(version_id, ids, workspace_id=workspace_id, project_id=project_id, kind="metric")

    def delete_dimensions(
        self, version_id: uuid.UUID, ids: list[str], *, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> BulkDeleteResponse:
        return self._delete(version_id, ids, workspace_id=workspace_id, project_id=project_id, kind="dimension")

    def delete_relationships(
        self, version_id: uuid.UUID, ids: list[str], *, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> BulkDeleteResponse:
        return self._delete(version_id, ids, workspace_id=workspace_id, project_id=project_id, kind="relationship")

    def delete_terms(
        self, version_id: uuid.UUID, ids: list[str], *, workspace_id: uuid.UUID, project_id: uuid.UUID
    ) -> BulkDeleteResponse:
        return self._delete(version_id, ids, workspace_id=workspace_id, project_id=project_id, kind="term")

    def _delete(
        self,
        version_id: uuid.UUID,
        ids: list[str],
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        kind: str,
    ) -> BulkDeleteResponse:
        if len(ids) > self._max_items():
            raise SemanticRegistryError(
                "bulk_limit",
                f"No more than {self._max_items()} items may be deleted at once",
                400,
            )
        deleted: list[BulkDeletedItem] = []
        failed: list[BulkFailedItem] = []
        deleters = {
            "entity": self._registry.delete_entity,
            "metric": self._registry.delete_metric,
            "dimension": self._registry.delete_dimension,
            "relationship": self._registry.delete_relationship,
            "term": self._registry.delete_term,
        }
        delete_fn = deleters[kind]
        for raw in ids:
            try:
                obj_id = uuid.UUID(str(raw).strip())
            except ValueError:
                failed.append(BulkFailedItem(id=raw, name=raw, code="invalid_id", message="Id is not valid"))
                continue
            name = str(obj_id)
            try:
                delete_fn(version_id, obj_id, workspace_id=workspace_id, project_id=project_id)
                deleted.append(BulkDeletedItem(id=str(obj_id), name=name))
            except SemanticRegistryError as exc:
                failed.append(BulkFailedItem(id=str(obj_id), name=name, code=exc.code, message=exc.message))
        self._session.commit()
        return BulkDeleteResponse(
            requested=len(ids),
            deleted=deleted,
            failed=failed,
            deleted_count=len(deleted),
            failed_count=len(failed),
        )
