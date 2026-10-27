from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.db.platform_models import (
    SemanticDimensionRow,
    SemanticEntityRow,
    SemanticMetricRow,
    SemanticRelationshipRow,
    SemanticModelRow,
    SemanticTermRow,
    SemanticVersionRow,
)
from app.semantic.registry import TempoOssieRegistry
from app.semantic_registry.validation import SemanticValidationService


def _stable_key(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return value or "item"


def _split_source(source: str) -> tuple[str | None, str | None, str | None]:
    parts = source.split(".")
    if len(parts) >= 2:
        return None, parts[0], parts[-1]
    if len(parts) == 1:
        return None, None, parts[0]
    return None, None, None


def _infer_aggregation(expression: str) -> str | None:
    upper = expression.strip().upper()
    for agg in ("SUM", "AVG", "COUNT", "MIN", "MAX"):
        if upper.startswith(f"{agg}("):
            return agg.lower()
    return None


@dataclass
class ImportSummary:
    entities: int = 0
    metrics: int = 0
    dimensions: int = 0
    relationships: int = 0
    terms: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    semantic_model_id: uuid.UUID | None = None
    semantic_version_id: uuid.UUID | None = None
    validation: dict | None = None

    def to_dict(self) -> dict:
        return {
            "imported": {
                "entities": self.entities,
                "metrics": self.metrics,
                "dimensions": self.dimensions,
                "relationships": self.relationships,
                "terms": self.terms,
            },
            "warnings": self.warnings,
            "errors": self.errors,
            "semantic_model_id": str(self.semantic_model_id) if self.semantic_model_id else None,
            "semantic_version_id": str(self.semantic_version_id) if self.semantic_version_id else None,
            "validation": self.validation,
        }


class OssieImporter:
    """Read-only bootstrap from on-disk OSSIE YAML into registry DRAFT."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def import_into_model(
        self,
        *,
        model: SemanticModelRow,
        project_dir: Path,
        source_type: str = "impala",
        dry_run: bool = False,
        created_by: str | None = "ossie_importer",
        draft_version: SemanticVersionRow | None = None,
    ) -> ImportSummary:
        summary = ImportSummary()
        project_dir = project_dir.resolve()
        if not (project_dir / "ossie" / "tempo_core.ossie.yaml").is_file():
            summary.errors.append(f"Missing tempo_core.ossie.yaml under {project_dir}")
            return summary

        try:
            registry = TempoOssieRegistry(project_dir)
        except Exception as exc:
            summary.errors.append(f"Failed to load OSSIE: {type(exc).__name__}: {exc}")
            return summary

        if dry_run:
            summary.entities = len(registry.datasets)
            summary.metrics = len(registry.metrics)
            for ds_name, ds in registry.datasets.items():
                for field in ds.get("fields", []):
                    if field.get("dimension") is not None:
                        summary.dimensions += 1
            summary.relationships = len(registry.model.get("relationships") or [])
            summary.warnings.append("dry_run: no database writes")
            return summary

        if draft_version is not None:
            if draft_version.semantic_model_id != model.id or draft_version.status != "DRAFT":
                summary.errors.append("Provided draft_version is not a DRAFT for this model")
                return summary
            version = draft_version
        else:
            version = SemanticVersionRow(
                semantic_model_id=model.id,
                version_number=self._next_version_number(model.id),
                status="DRAFT",
                created_by=created_by,
            )
            self._session.add(version)
            self._session.flush()

        for ds_name, dataset in sorted(registry.datasets.items(), key=lambda x: x[0]):
            source = str(dataset.get("source") or "")
            catalog, schema, table = _split_source(source)
            pk = dataset.get("primary_key") or []
            entity = SemanticEntityRow(
                semantic_version_id=version.id,
                key=_stable_key(ds_name),
                name=ds_name,
                description=dataset.get("description"),
                source_type=source_type,
                catalog=catalog,
                schema=schema,
                table_name=table,
                view_name=table,
                primary_key=",".join(pk) if isinstance(pk, list) else str(pk),
                metadata_={"ossie_dataset": ds_name, "source": source},
            )
            self._session.add(entity)
            summary.entities += 1

            for field in dataset.get("fields", []):
                if field.get("dimension") is None:
                    continue
                dim = SemanticDimensionRow(
                    semantic_version_id=version.id,
                    key=_stable_key(f"{ds_name}_{field['name']}"),
                    name=str(field.get("label") or field["name"]),
                    description=None,
                    source_entity_key=_stable_key(ds_name),
                    source_column=field["name"],
                    data_type=str(field.get("datatype") or ""),
                    synonyms=list((field.get("ai_context") or {}).get("synonyms") or []),
                    metadata_={"ossie_field": field["name"]},
                )
                self._session.add(dim)
                summary.dimensions += 1

        for metric_name, metric in sorted(registry.metrics.items(), key=lambda x: x[0]):
            config = registry.metric_configs.get(metric_name) or {}
            base_dataset = config.get("base_dataset") or metric_name
            try:
                expression = registry.ansi_expression(metric)
            except ValueError:
                expression = ""
                summary.warnings.append(f"Metric {metric_name}: missing ANSI expression")
            ai_ctx = metric.get("ai_context") or {}
            row = SemanticMetricRow(
                semantic_version_id=version.id,
                key=_stable_key(metric_name),
                name=metric_name,
                description=metric.get("description"),
                business_definition=str(ai_ctx.get("instructions") or metric.get("description") or ""),
                expression=expression,
                aggregation=_infer_aggregation(expression),
                source_entity_key=_stable_key(str(base_dataset)),
                format=str(config.get("unit_format") or "") or None,
                unit=None,
                synonyms=list(ai_ctx.get("synonyms") or []),
                metadata_={"ossie_metric": metric_name, "tempo_extension": config},
            )
            self._session.add(row)
            summary.metrics += 1

        for idx, rel in enumerate(registry.model.get("relationships") or []):
            if not isinstance(rel, dict):
                continue
            key = _stable_key(str(rel.get("name") or f"relationship_{idx}"))
            row = SemanticRelationshipRow(
                semantic_version_id=version.id,
                key=key,
                name=str(rel.get("name") or key),
                from_entity_key=_stable_key(str(rel.get("from") or rel.get("from_entity") or "")),
                to_entity_key=_stable_key(str(rel.get("to") or rel.get("to_entity") or "")),
                relationship_type=str(rel.get("relationship_type") or "many_to_one"),
                join_type=str(rel.get("join_type") or "inner"),
                join_expression=str(rel.get("join_expression") or rel.get("expression") or ""),
                description=rel.get("description"),
                metadata_={"ossie_relationship": rel},
            )
            self._session.add(row)
            summary.relationships += 1

        model_ai = registry.model.get("ai_context") or {}
        for idx, synonym in enumerate(model_ai.get("synonyms") or []):
            term_key = _stable_key(str(synonym))
            term = SemanticTermRow(
                semantic_version_id=version.id,
                key=f"model_term_{term_key}_{idx}",
                term=str(synonym),
                definition=str(model_ai.get("instructions") or "")[:2000] or None,
                synonyms=[],
                related_metric_keys=[],
                related_dimension_keys=[],
                related_entity_keys=[],
                metadata_={"source": "model_ai_context"},
            )
            self._session.add(term)
            summary.terms += 1

        for metric_name, metric in registry.metrics.items():
            ai_ctx = metric.get("ai_context") or {}
            for idx, synonym in enumerate(ai_ctx.get("synonyms") or []):
                term_key = _stable_key(f"{metric_name}_{synonym}")
                term = SemanticTermRow(
                    semantic_version_id=version.id,
                    key=f"metric_{term_key}_{idx}",
                    term=str(synonym),
                    definition=metric.get("description"),
                    synonyms=[],
                    related_metric_keys=[_stable_key(metric_name)],
                    related_dimension_keys=[],
                    related_entity_keys=[],
                    metadata_={"source": "metric_ai_context", "ossie_metric": metric_name},
                )
                self._session.add(term)
                summary.terms += 1

        self._session.flush()
        validation = SemanticValidationService(self._session).validate_version(version.id)
        summary.validation = validation.to_dict()
        summary.semantic_model_id = model.id
        summary.semantic_version_id = version.id
        if not validation.valid:
            summary.warnings.append("Imported draft has validation errors; fix before publish")
        return summary

    def _next_version_number(self, model_id: uuid.UUID) -> int:
        from sqlalchemy import func, select

        current = (
            self._session.scalar(
                select(func.coalesce(func.max(SemanticVersionRow.version_number), 0)).where(
                    SemanticVersionRow.semantic_model_id == model_id
                )
            )
            or 0
        )
        return int(current) + 1
