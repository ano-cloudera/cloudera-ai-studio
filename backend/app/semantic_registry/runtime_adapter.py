from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT
from app.db.platform_models import (
    SemanticDimensionRow,
    SemanticEntityRow,
    SemanticMetricRow,
    SemanticRelationshipRow,
    SemanticTermRow,
    SemanticVersionRow,
)
from app.semantic_registry.types import RuntimeArtifact


class SemanticRuntimeAdapter:
    adapter_name: str = "base"

    def generate_artifact(self, session: Session, version_id: uuid.UUID, *, write_file: bool = False) -> RuntimeArtifact:
        raise NotImplementedError


class OssieRuntimeAdapter(SemanticRuntimeAdapter):
    adapter_name = "ossie"

    def generate_artifact(self, session: Session, version_id: uuid.UUID, *, write_file: bool = False) -> RuntimeArtifact:
        version = session.get(SemanticVersionRow, version_id)
        if not version:
            raise ValueError("Semantic version not found")

        entities = session.execute(
            select(SemanticEntityRow)
            .where(SemanticEntityRow.semantic_version_id == version_id)
            .order_by(SemanticEntityRow.key)
        ).scalars().all()
        metrics = session.execute(
            select(SemanticMetricRow)
            .where(SemanticMetricRow.semantic_version_id == version_id)
            .order_by(SemanticMetricRow.key)
        ).scalars().all()
        dimensions = session.execute(
            select(SemanticDimensionRow).where(SemanticDimensionRow.semantic_version_id == version_id)
        ).scalars().all()
        relationships = session.execute(
            select(SemanticRelationshipRow)
            .where(SemanticRelationshipRow.semantic_version_id == version_id)
            .order_by(SemanticRelationshipRow.key)
        ).scalars().all()
        terms = session.execute(
            select(SemanticTermRow).where(SemanticTermRow.semantic_version_id == version_id).order_by(SemanticTermRow.key)
        ).scalars().all()

        dims_by_entity: dict[str, list[SemanticDimensionRow]] = {}
        for dim in dimensions:
            dims_by_entity.setdefault(dim.source_entity_key, []).append(dim)

        datasets: list[dict[str, Any]] = []
        for entity in entities:
            fields = []
            for dim in sorted(dims_by_entity.get(entity.key, []), key=lambda d: d.key):
                field: dict[str, Any] = {
                    "name": dim.key,
                    "expression": {
                        "dialects": [{"dialect": "ANSI_SQL", "expression": dim.source_column}],
                    },
                    "datatype": dim.data_type or "String",
                    "dimension": {},
                }
                if (dim.data_type or "").casefold() in {"date", "timestamp", "datetime"} or (
                    dim.metadata_ or {}
                ).get("is_time"):
                    field["dimension"] = {"is_time": True}
                fields.append(field)
            source = entity.metadata_.get("source") if entity.metadata_ else None
            if not source and entity.schema and (entity.table_name or entity.view_name):
                source = f"{entity.schema}.{entity.table_name or entity.view_name}"
            pk = [p.strip() for p in (entity.primary_key or "").split(",") if p.strip()]
            datasets.append(
                {
                    "name": entity.key,
                    "source": source or "",
                    "primary_key": pk,
                    "description": entity.description or entity.name,
                    "fields": fields,
                }
            )

        metric_docs: list[dict[str, Any]] = []
        for metric in metrics:
            entity_dims = dims_by_entity.get(metric.source_entity_key, [])
            allowed_dimension_keys = [d.key for d in sorted(entity_dims, key=lambda d: d.key)]
            doc: dict[str, Any] = {
                "name": metric.key,
                "expression": {
                    "dialects": [{"dialect": "ANSI_SQL", "expression": metric.expression}],
                },
                "datatype": "Decimal",
                "description": metric.description or metric.business_definition or metric.name,
            }
            if metric.synonyms:
                doc["ai_context"] = {"synonyms": list(metric.synonyms)}
            tempo_payload = {
                "base_dataset": metric.metadata_.get("ossie_dataset") or metric.source_entity_key,
                "allowed_dimensions": allowed_dimension_keys,
            }
            if metric.metadata_ and isinstance(metric.metadata_.get("tempo_extension"), dict):
                tempo_payload.update(metric.metadata_["tempo_extension"])
            doc["custom_extensions"] = [{"vendor_name": "TEMPO", "data": __import__("json").dumps(tempo_payload)}]
            metric_docs.append(doc)

        rel_docs = []
        for rel in relationships:
            rel_docs.append(
                {
                    "name": rel.name,
                    "from": rel.from_entity_key,
                    "to": rel.to_entity_key,
                    "relationship_type": rel.relationship_type,
                    "join_type": rel.join_type,
                    "join_expression": rel.join_expression,
                    "description": rel.description,
                }
            )

        glossary_synonyms = sorted({t.term for t in terms})
        payload = {
            "version": "0.2.0.dev0",
            "name": f"registry_v{version.version_number}",
            "description": "Generated from PostgreSQL Semantic Registry (preview)",
            "ai_context": {
                "instructions": "Generated artifact — do not edit manually.",
                "synonyms": glossary_synonyms[:50],
            },
            "datasets": datasets,
            "relationships": rel_docs,
            "metrics": metric_docs,
            "_registry_terms_count": len(terms),
        }

        content = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        uri: str | None = None
        if write_file:
            from app.db.platform_models import SemanticModelRow

            model = session.get(SemanticModelRow, version.semantic_model_id)
            if not model:
                raise ValueError("Semantic model not found")
            base = BACKEND_ROOT / "var" / "semantic-artifacts" / str(model.workspace_id) / str(model.project_id)
            dest = base / model.key / f"v{version.version_number}" / "ossie.yaml"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            uri = str(dest.relative_to(BACKEND_ROOT))

        return RuntimeArtifact(
            adapter=self.adapter_name,
            version=str(version.version_number),
            uri=uri,
            checksum=checksum,
            content_preview=content[:8000],
            content=content,
            metadata={
                "entities": len(entities),
                "metrics": len(metrics),
                "dimensions": len(dimensions),
                "relationships": len(relationships),
                "entity_count": len(entities),
                "metric_count": len(metrics),
                "dimension_count": len(dimensions),
                "relationship_count": len(relationships),
            },
        )
