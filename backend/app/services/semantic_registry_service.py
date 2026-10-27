from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.platform_models import (
    SemanticDimensionRow,
    SemanticEntityRow,
    SemanticMetricRow,
    SemanticModelRow,
    SemanticRelationshipRow,
    SemanticTermRow,
    SemanticVersionRow,
)
from app.semantic_registry.governance_types import READINESS_NOT_READY
from app.semantic_registry.runtime_adapter import OssieRuntimeAdapter
from app.semantic_registry.semantic_diff import SemanticDiffService
from app.semantic_registry.source_validators import ImpalaSemanticSourceValidator, TrinoSemanticSourceValidator
from app.semantic_registry.types import ResolvedSemantic
from app.semantic_registry.registry_errors import SemanticRegistryError  # noqa: F401 — re-exported API surface
from app.semantic_registry.validation import SemanticValidationService
from app.db.platform_models import SemanticValidationIssueRow, SemanticValidationRunRow


@dataclass
class SemanticModelCreate:
    name: str
    key: str
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    description: str | None = None


class SemanticRegistryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_models(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        search: str | None = None,
    ) -> list[SemanticModelRow]:
        q = select(SemanticModelRow).where(
            SemanticModelRow.workspace_id == workspace_id,
            SemanticModelRow.project_id == project_id,
        )
        rows = list(self._session.execute(q.order_by(SemanticModelRow.key)).scalars().all())
        if search:
            needle = search.strip().lower()
            rows = [r for r in rows if needle in r.name.lower() or needle in r.key.lower()]
        return rows

    def get_model(self, model_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> SemanticModelRow:
        row = self._session.get(SemanticModelRow, model_id)
        if not row or row.workspace_id != workspace_id or row.project_id != project_id:
            raise SemanticRegistryError("not_found", "Semantic model not found", 404)
        return row

    def create_model(self, body: SemanticModelCreate) -> SemanticModelRow:
        if self._find_model(body.project_id, body.key):
            raise SemanticRegistryError("duplicate", "Semantic model key already exists for project", 409)
        row = SemanticModelRow(
            name=body.name.strip(),
            key=body.key.strip(),
            description=(body.description or "").strip() or None,
            workspace_id=body.workspace_id,
            project_id=body.project_id,
        )
        self._session.add(row)
        self._session.flush()
        self.create_version(row.id, workspace_id=body.workspace_id, project_id=body.project_id)
        self._session.refresh(row)
        return row

    def patch_model(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> SemanticModelRow:
        row = self.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        if name is not None:
            row.name = name.strip()
        if description is not None:
            row.description = description.strip() or None
        self._session.flush()
        return row

    def create_version(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        created_by: str | None = None,
    ) -> SemanticVersionRow:
        model = self.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        next_num = (
            self._session.scalar(
                select(func.coalesce(func.max(SemanticVersionRow.version_number), 0)).where(
                    SemanticVersionRow.semantic_model_id == model_id
                )
            )
            or 0
        ) + 1
        version = SemanticVersionRow(
            semantic_model_id=model.id,
            version_number=int(next_num),
            status="DRAFT",
            created_by=created_by,
        )
        self._session.add(version)
        self._session.flush()
        return version

    def list_versions(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> list[SemanticVersionRow]:
        self.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        return list(
            self._session.execute(
                select(SemanticVersionRow)
                .where(SemanticVersionRow.semantic_model_id == model_id)
                .order_by(SemanticVersionRow.version_number.desc())
            ).scalars().all()
        )

    def get_version(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> SemanticVersionRow:
        version = self._session.get(SemanticVersionRow, version_id)
        if not version:
            raise SemanticRegistryError("not_found", "Semantic version not found", 404)
        self.get_model(version.semantic_model_id, workspace_id=workspace_id, project_id=project_id)
        return version

    def clone_version(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        created_by: str | None = None,
    ) -> SemanticVersionRow:
        source = self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        draft = self.create_version(
            source.semantic_model_id,
            workspace_id=workspace_id,
            project_id=project_id,
            created_by=created_by,
        )
        self._copy_version_content(source.id, draft.id)
        self._session.refresh(draft)
        return draft

    def validate_version(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        mode: str = "full",
        source_mode: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return (
            SemanticValidationService(self._session)
            .validate_version(version_id, mode=mode, source_mode=source_mode, created_by=created_by)
            .to_dict()
        )

    def get_readiness(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        version = self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return {
            "semantic_version_id": str(version_id),
            "activation_readiness": version.activation_readiness,
            "validated_at": version.validated_at,
            "last_validation_run_id": str(version.last_validation_run_id) if version.last_validation_run_id else None,
        }

    def list_validation_runs(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int = 20,
    ) -> list[SemanticValidationRunRow]:
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return list(
            self._session.execute(
                select(SemanticValidationRunRow)
                .where(SemanticValidationRunRow.semantic_version_id == version_id)
                .order_by(SemanticValidationRunRow.started_at.desc())
                .limit(limit)
            ).scalars().all()
        )

    def get_validation_run(
        self,
        run_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        run = self._session.get(SemanticValidationRunRow, run_id)
        if not run:
            raise SemanticRegistryError("not_found", "Validation run not found", 404)
        self.get_version(run.semantic_version_id, workspace_id=workspace_id, project_id=project_id)
        issues = list(
            self._session.execute(
                select(SemanticValidationIssueRow).where(SemanticValidationIssueRow.validation_run_id == run_id)
            ).scalars().all()
        )
        return {
            "run": {
                "id": str(run.id),
                "semantic_version_id": str(run.semantic_version_id),
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "status": run.status,
                "mode": run.mode,
                "summary": run.summary,
                "validator_version": run.validator_version,
            },
            "issues": [
                {
                    "id": str(i.id),
                    "severity": i.severity,
                    "category": i.category,
                    "object_type": i.object_type,
                    "object_key": i.object_key,
                    "code": i.code,
                    "message": i.message,
                    "remediation": i.remediation,
                    "metadata": i.metadata_ or {},
                }
                for i in issues
            ],
        }

    def diff_version(
        self,
        version_id: uuid.UUID,
        *,
        against_version_id: uuid.UUID,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        self.get_version(against_version_id, workspace_id=workspace_id, project_id=project_id)
        return SemanticDiffService(self._session).diff_versions(version_id, against_version_id)

    def source_validator_health(self) -> dict:
        from app.core.config import get_settings

        settings = get_settings()
        impala_status, impala_label = ImpalaSemanticSourceValidator(settings).health()
        trino_status, trino_label = TrinoSemanticSourceValidator(settings).health()
        return {
            "impala": {"status": impala_status, "label": impala_label},
            "trino": {"status": trino_status, "label": trino_label},
        }

    def publish_version(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        artifact_preview: bool = True,
    ) -> SemanticVersionRow:
        version = self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        if version.status != "DRAFT":
            raise SemanticRegistryError("invalid_state", "Only DRAFT versions can be published", 409)
        validation = SemanticValidationService(self._session).validate_version(version_id, mode="full")
        if not validation.valid or validation.summary.readiness == READINESS_NOT_READY:
            raise SemanticRegistryError("validation_failed", "Publish blocked by validation errors", 422)

        model = self.get_model(version.semantic_model_id, workspace_id=workspace_id, project_id=project_id)
        if artifact_preview:
            artifact = OssieRuntimeAdapter().generate_artifact(self._session, version_id, write_file=True)
            version.runtime_adapter = artifact.adapter
            version.runtime_artifact_uri = artifact.uri
            version.runtime_artifact_checksum = artifact.checksum
            version.runtime_artifact_version = artifact.version

        self._activate_version(model, version)
        version.published_at = datetime.now(timezone.utc)
        self._session.flush()
        self._session.refresh(version)
        return version

    def rollback_version(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> SemanticVersionRow:
        version = self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        if version.status == "ARCHIVED":
            model = self.get_model(version.semantic_model_id, workspace_id=workspace_id, project_id=project_id)
            self._activate_version(model, version)
            version.published_at = datetime.now(timezone.utc)
            self._session.flush()
            self._session.refresh(version)
            return version
        if version.status == "ACTIVE":
            return version
        raise SemanticRegistryError("invalid_state", "Rollback requires ARCHIVED or ACTIVE version", 409)

    def artifact_preview(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        write_file: bool = False,
    ) -> dict:
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        artifact = OssieRuntimeAdapter().generate_artifact(self._session, version_id, write_file=write_file)
        return {
            "adapter": artifact.adapter,
            "version": artifact.version,
            "uri": artifact.uri,
            "checksum": artifact.checksum,
            "content_preview": artifact.content_preview,
            "metadata": artifact.metadata,
        }

    def resolve_active(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        semantic_model_key: str,
    ) -> ResolvedSemantic | None:
        model = self._find_model(project_id, semantic_model_key)
        if not model or model.workspace_id != workspace_id:
            return None
        if not model.active_version_id:
            return None
        version = self._session.get(SemanticVersionRow, model.active_version_id)
        if not version or version.status != "ACTIVE":
            return None
        return ResolvedSemantic(model=model, version=version)

    def _activate_version(self, model: SemanticModelRow, version: SemanticVersionRow) -> None:
        active_rows = self._session.execute(
            select(SemanticVersionRow).where(
                SemanticVersionRow.semantic_model_id == model.id,
                SemanticVersionRow.status == "ACTIVE",
            )
        ).scalars().all()
        for row in active_rows:
            if row.id != version.id:
                row.status = "ARCHIVED"
        version.status = "ACTIVE"
        model.active_version_id = version.id
        self._session.flush()

    def _find_model(self, project_id: uuid.UUID, key: str) -> SemanticModelRow | None:
        return self._session.execute(
            select(SemanticModelRow).where(SemanticModelRow.project_id == project_id, SemanticModelRow.key == key)
        ).scalar_one_or_none()

    def _copy_version_content(self, source_version_id: uuid.UUID, target_version_id: uuid.UUID) -> None:
        for model_cls, mapper in (
            (SemanticEntityRow, lambda r: SemanticEntityRow(
                semantic_version_id=target_version_id,
                key=r.key,
                name=r.name,
                description=r.description,
                source_type=r.source_type,
                catalog=r.catalog,
                schema=r.schema,
                table_name=r.table_name,
                view_name=r.view_name,
                primary_key=r.primary_key,
                metadata_=dict(r.metadata_ or {}),
            )),
            (SemanticMetricRow, lambda r: SemanticMetricRow(
                semantic_version_id=target_version_id,
                key=r.key,
                name=r.name,
                description=r.description,
                business_definition=r.business_definition,
                expression=r.expression,
                aggregation=r.aggregation,
                source_entity_key=r.source_entity_key,
                format=r.format,
                unit=r.unit,
                synonyms=list(r.synonyms or []),
                metadata_=dict(r.metadata_ or {}),
            )),
            (SemanticDimensionRow, lambda r: SemanticDimensionRow(
                semantic_version_id=target_version_id,
                key=r.key,
                name=r.name,
                description=r.description,
                source_entity_key=r.source_entity_key,
                source_column=r.source_column,
                data_type=r.data_type,
                synonyms=list(r.synonyms or []),
                metadata_=dict(r.metadata_ or {}),
            )),
            (SemanticRelationshipRow, lambda r: SemanticRelationshipRow(
                semantic_version_id=target_version_id,
                key=r.key,
                name=r.name,
                from_entity_key=r.from_entity_key,
                to_entity_key=r.to_entity_key,
                relationship_type=r.relationship_type,
                join_type=r.join_type,
                join_expression=r.join_expression,
                description=r.description,
                metadata_=dict(r.metadata_ or {}),
            )),
            (SemanticTermRow, lambda r: SemanticTermRow(
                semantic_version_id=target_version_id,
                key=r.key,
                term=r.term,
                definition=r.definition,
                synonyms=list(r.synonyms or []),
                related_metric_keys=list(r.related_metric_keys or []),
                related_dimension_keys=list(r.related_dimension_keys or []),
                related_entity_keys=list(r.related_entity_keys or []),
                metadata_=dict(r.metadata_ or {}),
            )),
        ):
            rows = self._session.execute(
                select(model_cls).where(model_cls.semantic_version_id == source_version_id)
            ).scalars().all()
            for row in rows:
                self._session.add(mapper(row))

        self._session.flush()

    def _require_draft(self, version: SemanticVersionRow) -> None:
        if version.status != "DRAFT":
            raise SemanticRegistryError("immutable_version", "Only DRAFT semantic versions are editable", 409)

    def ensure_draft_version(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> SemanticVersionRow:
        version = self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        self._require_draft(version)
        return version

    # --- Semantic objects (DRAFT only) ---

    def list_entities(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return list(
            self._session.execute(
                select(SemanticEntityRow)
                .where(SemanticEntityRow.semantic_version_id == version_id)
                .order_by(SemanticEntityRow.key)
            ).scalars().all()
        )

    def create_entity(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID, data: dict):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        connection_id = data.get("connection_id")
        conn_uuid: uuid.UUID | None = None
        if connection_id:
            from app.semantic_registry.connector_reference import validate_entity_connector

            validate_entity_connector(
                self._session,
                connection_id=uuid.UUID(str(connection_id)),
                workspace_id=workspace_id,
                project_id=project_id,
                source_type=data.get("source_type"),
                require_enabled=False,
            )
            conn_uuid = uuid.UUID(str(connection_id))
        row = SemanticEntityRow(
            semantic_version_id=version_id,
            key=data["key"].strip(),
            name=data["name"].strip(),
            description=data.get("description"),
            source_type=data.get("source_type") or "logical",
            catalog=data.get("catalog"),
            schema=data.get("db_schema") or data.get("schema"),
            table_name=data.get("table_name"),
            view_name=data.get("view_name"),
            primary_key=data.get("primary_key"),
            connection_id=conn_uuid,
            metadata_=dict(data.get("metadata") or {}),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def delete_entity(self, version_id: uuid.UUID, entity_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticEntityRow, entity_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Entity not found", 404)
        self._session.delete(row)

    def delete_metric(self, version_id: uuid.UUID, metric_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticMetricRow, metric_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Metric not found", 404)
        self._session.delete(row)

    def delete_dimension(self, version_id: uuid.UUID, dimension_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticDimensionRow, dimension_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Dimension not found", 404)
        self._session.delete(row)

    def delete_relationship(self, version_id: uuid.UUID, relationship_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticRelationshipRow, relationship_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Relationship not found", 404)
        self._session.delete(row)

    def delete_term(self, version_id: uuid.UUID, term_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticTermRow, term_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Term not found", 404)
        self._session.delete(row)

    def list_metrics(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return list(
            self._session.execute(
                select(SemanticMetricRow).where(SemanticMetricRow.semantic_version_id == version_id).order_by(SemanticMetricRow.key)
            ).scalars().all()
        )

    def create_metric(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID, data: dict):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = SemanticMetricRow(
            semantic_version_id=version_id,
            key=data["key"].strip(),
            name=data["name"].strip(),
            description=data.get("description"),
            business_definition=data.get("business_definition"),
            expression=data["expression"],
            aggregation=data.get("aggregation"),
            source_entity_key=data["source_entity_key"],
            format=data.get("format"),
            unit=data.get("unit"),
            synonyms=list(data.get("synonyms") or []),
            metadata_=dict(data.get("metadata") or {}),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list_dimensions(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return list(
            self._session.execute(
                select(SemanticDimensionRow)
                .where(SemanticDimensionRow.semantic_version_id == version_id)
                .order_by(SemanticDimensionRow.key)
            ).scalars().all()
        )

    def create_dimension(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID, data: dict):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = SemanticDimensionRow(
            semantic_version_id=version_id,
            key=data["key"].strip(),
            name=data["name"].strip(),
            description=data.get("description"),
            source_entity_key=data["source_entity_key"],
            source_column=data["source_column"],
            data_type=data.get("data_type"),
            synonyms=list(data.get("synonyms") or []),
            metadata_=dict(data.get("metadata") or {}),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list_relationships(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return list(
            self._session.execute(
                select(SemanticRelationshipRow)
                .where(SemanticRelationshipRow.semantic_version_id == version_id)
                .order_by(SemanticRelationshipRow.key)
            ).scalars().all()
        )

    def create_relationship(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID, data: dict):
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = SemanticRelationshipRow(
            semantic_version_id=version_id,
            key=data["key"].strip(),
            name=data["name"].strip(),
            from_entity_key=data["from_entity_key"],
            to_entity_key=data["to_entity_key"],
            relationship_type=data.get("relationship_type") or "many_to_one",
            join_type=data.get("join_type") or "inner",
            join_expression=data["join_expression"],
            description=data.get("description"),
            metadata_=dict(data.get("metadata") or {}),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list_terms(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        self.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
        return list(
            self._session.execute(
                select(SemanticTermRow).where(SemanticTermRow.semantic_version_id == version_id).order_by(SemanticTermRow.key)
            ).scalars().all()
        )

    def create_term(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID, data: dict):
        from app.semantic_registry.term_relations import normalize_term_related_keys, validate_term_related_keys

        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        mk, dk, ek = normalize_term_related_keys(
            related_metric_keys=data.get("related_metric_keys"),
            related_dimension_keys=data.get("related_dimension_keys"),
            related_entity_keys=data.get("related_entity_keys"),
        )
        validate_term_related_keys(self._session, version_id, related_metric_keys=mk, related_dimension_keys=dk, related_entity_keys=ek)
        row = SemanticTermRow(
            semantic_version_id=version_id,
            key=data["key"].strip(),
            term=data["term"].strip(),
            definition=data.get("definition"),
            synonyms=list(data.get("synonyms") or []),
            related_metric_keys=mk,
            related_dimension_keys=dk,
            related_entity_keys=ek,
            metadata_=dict(data.get("metadata") or {}),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def _find_draft_version(self, model_id: uuid.UUID) -> SemanticVersionRow | None:
        return self._session.execute(
            select(SemanticVersionRow)
            .where(SemanticVersionRow.semantic_model_id == model_id, SemanticVersionRow.status == "DRAFT")
            .order_by(SemanticVersionRow.version_number.desc())
        ).scalars().first()

    def update_entity(
        self,
        version_id: uuid.UUID,
        entity_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        data: dict,
    ) -> SemanticEntityRow:
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticEntityRow, entity_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Entity not found", 404)
        if "name" in data and data["name"] is not None:
            row.name = str(data["name"]).strip()
        for field, key in (
            ("description", "description"),
            ("source_type", "source_type"),
            ("catalog", "catalog"),
            ("table_name", "table_name"),
            ("view_name", "view_name"),
            ("primary_key", "primary_key"),
        ):
            if key in data:
                setattr(row, field, data[key])
        if "db_schema" in data or "schema" in data:
            row.schema = data.get("db_schema") if "db_schema" in data else data.get("schema")
        if "metadata" in data and data["metadata"] is not None:
            row.metadata_ = dict(data["metadata"])
        if "connection_id" in data:
            from app.semantic_registry.connector_reference import validate_entity_connector

            raw = data["connection_id"]
            if raw is None:
                row.connection_id = None
            else:
                validate_entity_connector(
                    self._session,
                    connection_id=uuid.UUID(str(raw)),
                    workspace_id=workspace_id,
                    project_id=project_id,
                    source_type=data.get("source_type") or row.source_type,
                    require_enabled=False,
                )
                row.connection_id = uuid.UUID(str(raw))
        self._session.flush()
        return row

    def update_metric(
        self,
        version_id: uuid.UUID,
        metric_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        data: dict,
    ) -> SemanticMetricRow:
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticMetricRow, metric_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Metric not found", 404)
        for field in (
            "name",
            "description",
            "business_definition",
            "expression",
            "aggregation",
            "source_entity_key",
            "format",
            "unit",
        ):
            if field in data and data[field] is not None:
                setattr(row, field, data[field])
        if "synonyms" in data and data["synonyms"] is not None:
            row.synonyms = list(data["synonyms"])
        if "metadata" in data and data["metadata"] is not None:
            row.metadata_ = dict(data["metadata"])
        self._session.flush()
        return row

    def update_dimension(
        self,
        version_id: uuid.UUID,
        dimension_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        data: dict,
    ) -> SemanticDimensionRow:
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticDimensionRow, dimension_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Dimension not found", 404)
        for field in ("name", "description", "source_entity_key", "source_column", "data_type"):
            if field in data and data[field] is not None:
                setattr(row, field, data[field])
        if "synonyms" in data and data["synonyms"] is not None:
            row.synonyms = list(data["synonyms"])
        self._session.flush()
        return row

    def update_relationship(
        self,
        version_id: uuid.UUID,
        relationship_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        data: dict,
    ) -> SemanticRelationshipRow:
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticRelationshipRow, relationship_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Relationship not found", 404)
        for field in (
            "name",
            "from_entity_key",
            "to_entity_key",
            "relationship_type",
            "join_type",
            "join_expression",
            "description",
        ):
            if field in data and data[field] is not None:
                setattr(row, field, data[field])
        self._session.flush()
        return row

    def update_term(
        self,
        version_id: uuid.UUID,
        term_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        data: dict,
    ) -> SemanticTermRow:
        self.ensure_draft_version(version_id, workspace_id=workspace_id, project_id=project_id)
        row = self._session.get(SemanticTermRow, term_id)
        if not row or row.semantic_version_id != version_id:
            raise SemanticRegistryError("not_found", "Term not found", 404)
        for field in ("term", "definition"):
            if field in data and data[field] is not None:
                setattr(row, field, data[field])
        from app.semantic_registry.term_relations import normalize_term_related_keys, validate_term_related_keys

        for field in ("synonyms",):
            if field in data and data[field] is not None:
                setattr(row, field, list(data[field]))
        mk = row.related_metric_keys
        dk = row.related_dimension_keys
        ek = row.related_entity_keys
        if "related_metric_keys" in data and data["related_metric_keys"] is not None:
            mk, _, _ = normalize_term_related_keys(
                related_metric_keys=data["related_metric_keys"],
                related_dimension_keys=[],
                related_entity_keys=[],
            )
        if "related_dimension_keys" in data and data["related_dimension_keys"] is not None:
            _, dk, _ = normalize_term_related_keys(
                related_metric_keys=[],
                related_dimension_keys=data["related_dimension_keys"],
                related_entity_keys=[],
            )
        if "related_entity_keys" in data and data["related_entity_keys"] is not None:
            _, _, ek = normalize_term_related_keys(
                related_metric_keys=[],
                related_dimension_keys=[],
                related_entity_keys=data["related_entity_keys"],
            )
        validate_term_related_keys(
            self._session, version_id, related_metric_keys=list(mk or []), related_dimension_keys=list(dk or []), related_entity_keys=list(ek or [])
        )
        row.related_metric_keys = list(mk or [])
        row.related_dimension_keys = list(dk or [])
        row.related_entity_keys = list(ek or [])
        self._session.flush()
        return row

    def import_from_ossie(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        model_key: str,
        model_name: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        from pathlib import Path

        from app.core.config import get_settings
        from app.projects.resolver import resolve_ossie_project_dir
        from app.semantic_registry.importer import OssieImporter

        settings = get_settings()
        project_dir = Path(resolve_ossie_project_dir(settings))
        model = self._find_model(project_id, model_key.strip())
        draft_version = None
        if not model:
            model = self.create_model(
                SemanticModelCreate(
                    name=model_name or model_key.replace("_", " ").title(),
                    key=model_key.strip(),
                    workspace_id=workspace_id,
                    project_id=project_id,
                    description="Imported from OSSIE",
                )
            )
            draft_version = self._find_draft_version(model.id)
        elif self._find_draft_version(model.id):
            raise SemanticRegistryError(
                "draft_exists",
                "A DRAFT version already exists for this model; publish or discard before import",
                409,
            )
        return OssieImporter(self._session).import_into_model(
            model=model,
            project_dir=project_dir,
            dry_run=dry_run,
            draft_version=draft_version,
        ).to_dict()

    def ossie_import_source(self) -> dict:
        from pathlib import Path

        from app.core.config import get_settings
        from app.projects.resolver import resolve_ossie_project_dir

        settings = get_settings()
        project_dir = Path(resolve_ossie_project_dir(settings)).resolve()
        ossie_file = project_dir / "ossie" / "tempo_core.ossie.yaml"
        return {
            "project_dir": str(project_dir),
            "ossie_file": str(ossie_file),
            "exists": ossie_file.is_file(),
        }
