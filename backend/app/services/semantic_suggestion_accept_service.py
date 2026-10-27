"""Persist wizard suggestion selections through canonical registry create APIs."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.semantic_registry.registry_errors import SemanticRegistryError
from app.services.semantic_registry_service import SemanticRegistryService

_AGG_EXPR = re.compile(r"^(SUM|COUNT|AVG|MIN|MAX)\([^.)]+\.([^)]+)\)$", re.I)


def _normalize_metric_expression(expression: str) -> str:
    expr = (expression or "").strip()
    m = _AGG_EXPR.match(expr)
    if m:
        return f"{m.group(1).upper()}({m.group(2)})"
    return expr


def _infer_aggregation(expression: str) -> str | None:
    m = re.match(r"^(SUM|COUNT|AVG|MIN|MAX)\(", expression.strip(), re.I)
    return m.group(1).lower() if m else None


@dataclass
class AcceptConflict:
    suggestion_id: str
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"suggestion_id": self.suggestion_id, "code": self.code, "message": self.message}


@dataclass
class AcceptPersisted:
    suggestion_id: str
    object_type: str
    object_id: str
    object_key: str

    def to_dict(self) -> dict:
        return {
            "suggestion_id": self.suggestion_id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "object_key": self.object_key,
        }


@dataclass
class SuggestionAcceptResult:
    version_id: str
    persisted: list[AcceptPersisted] = field(default_factory=list)
    conflicts: list[AcceptConflict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "persisted": [p.to_dict() for p in self.persisted],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "counts": self.counts,
        }


class SemanticSuggestionAcceptService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._registry = SemanticRegistryService(session)

    def accept(
        self,
        model_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        version_id: uuid.UUID | None,
        bootstrap_tables: list[dict] | None,
        selections: list[dict],
    ) -> SuggestionAcceptResult:
        model = self._registry.get_model(model_id, workspace_id=workspace_id, project_id=project_id)
        version = self._resolve_draft(model_id, version_id, workspace_id=workspace_id, project_id=project_id)
        result = SuggestionAcceptResult(version_id=str(version.id))
        existing_keys = self._existing_keys(version.id, workspace_id=workspace_id, project_id=project_id)

        for raw in bootstrap_tables or []:
            self._bootstrap_entity(
                version.id,
                workspace_id=workspace_id,
                project_id=project_id,
                raw=raw,
                existing_keys=existing_keys,
                result=result,
            )

        for sel in selections:
            if not sel.get("accepted"):
                continue
            suggestion_id = str(sel.get("suggestion_id") or "")
            payload = dict(sel.get("payload") or {})
            changes = dict(sel.get("changes") or {})
            payload.update(changes)
            kind = str(sel.get("type") or suggestion_id.split(":", 1)[0] if ":" in suggestion_id else "")
            try:
                if kind == "entity":
                    self._create_entity(version.id, workspace_id, project_id, payload, existing_keys, suggestion_id, result)
                elif kind == "metric":
                    self._create_metric(version.id, workspace_id, project_id, payload, existing_keys, suggestion_id, result)
                elif kind == "dimension":
                    self._create_dimension(version.id, workspace_id, project_id, payload, existing_keys, suggestion_id, result)
                elif kind == "relationship":
                    self._create_relationship(version.id, workspace_id, project_id, payload, existing_keys, suggestion_id, result)
                elif kind in ("term", "glossary"):
                    self._create_term(version.id, workspace_id, project_id, payload, existing_keys, suggestion_id, result)
            except SemanticRegistryError as exc:
                if exc.code in ("duplicate", "conflict"):
                    result.conflicts.append(AcceptConflict(suggestion_id, exc.code, exc.message))
                else:
                    raise

        self._session.flush()
        result.counts = self._count_objects(version.id, workspace_id=workspace_id, project_id=project_id)
        return result

    def _resolve_draft(
        self,
        model_id: uuid.UUID,
        version_id: uuid.UUID | None,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ):
        if version_id:
            version = self._registry.get_version(version_id, workspace_id=workspace_id, project_id=project_id)
            if version.semantic_model_id != model_id:
                raise SemanticRegistryError("invalid_version", "Version does not belong to model", 422)
            if version.status != "DRAFT":
                raise SemanticRegistryError("not_draft", "Only draft versions accept suggestions", 422)
            return version
        versions = self._registry.list_versions(model_id, workspace_id=workspace_id, project_id=project_id)
        drafts = [v for v in versions if v.status == "DRAFT"]
        if not drafts:
            raise SemanticRegistryError("no_draft", "No draft version for model", 422)
        return max(drafts, key=lambda v: v.version_number or 0)

    def _existing_keys(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> set[str]:
        keys: set[str] = set()
        for coll, kind in (
            (self._registry.list_entities(version_id, workspace_id=workspace_id, project_id=project_id), "entity"),
            (self._registry.list_metrics(version_id, workspace_id=workspace_id, project_id=project_id), "metric"),
            (self._registry.list_dimensions(version_id, workspace_id=workspace_id, project_id=project_id), "dimension"),
            (self._registry.list_relationships(version_id, workspace_id=workspace_id, project_id=project_id), "relationship"),
            (self._registry.list_terms(version_id, workspace_id=workspace_id, project_id=project_id), "term"),
        ):
            for row in coll:
                keys.add(f"{kind}:{row.key}")
        return keys

    def _bootstrap_entity(
        self,
        version_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        raw: dict,
        existing_keys: set[str],
        result: SuggestionAcceptResult,
    ) -> None:
        key = str(raw.get("key") or "").strip()
        sid = f"entity:{key}"
        if not key or f"entity:{key}" in existing_keys:
            return
        payload = {
            "key": key,
            "name": raw.get("name") or key,
            "description": raw.get("description"),
            "source_type": "logical",
            "connection_id": raw.get("connection_id"),
            "catalog": raw.get("catalog"),
            "schema": raw.get("schema"),
            "table_name": raw.get("table_name"),
            "primary_key": raw.get("primary_key"),
        }
        self._create_entity(version_id, workspace_id, project_id, payload, existing_keys, sid, result)

    def _create_entity(self, version_id, ws, proj, payload, existing_keys, sid, result):
        key = str(payload.get("key") or "").strip()
        if not key:
            return
        if f"entity:{key}" in existing_keys:
            result.conflicts.append(AcceptConflict(sid, "duplicate", f"Data model `{key}` already exists."))
            return
        row = self._registry.create_entity(version_id, workspace_id=ws, project_id=proj, data={**payload, "key": key})
        existing_keys.add(f"entity:{key}")
        result.persisted.append(AcceptPersisted(sid, "entity", str(row.id), key))

    def _create_metric(self, version_id, ws, proj, payload, existing_keys, sid, result):
        key = str(payload.get("key") or "").strip()
        if not key:
            return
        if f"metric:{key}" in existing_keys:
            result.conflicts.append(AcceptConflict(sid, "duplicate", f"Metric `{key}` already exists."))
            return
        expr = _normalize_metric_expression(str(payload.get("expression") or ""))
        row = self._registry.create_metric(
            version_id,
            workspace_id=ws,
            project_id=proj,
            data={
                "key": key,
                "name": payload.get("name") or key,
                "business_definition": payload.get("business_definition") or payload.get("description") or f"Suggested metric {key}",
                "expression": expr,
                "aggregation": payload.get("aggregation") or _infer_aggregation(expr),
                "source_entity_key": payload.get("source_entity_key"),
                "synonyms": payload.get("synonyms") or [],
            },
        )
        existing_keys.add(f"metric:{key}")
        result.persisted.append(AcceptPersisted(sid, "metric", str(row.id), key))

    def _create_dimension(self, version_id, ws, proj, payload, existing_keys, sid, result):
        key = str(payload.get("key") or "").strip()
        if not key:
            return
        if f"dimension:{key}" in existing_keys:
            result.conflicts.append(AcceptConflict(sid, "duplicate", f"Dimension `{key}` already exists."))
            return
        row = self._registry.create_dimension(
            version_id,
            workspace_id=ws,
            project_id=proj,
            data={
                "key": key,
                "name": payload.get("name") or key,
                "description": payload.get("description"),
                "source_entity_key": payload.get("source_entity_key"),
                "source_column": payload.get("source_column"),
                "data_type": payload.get("data_type") or "string",
                "synonyms": payload.get("synonyms") or [],
                "metadata": {"category": payload.get("category")} if payload.get("category") else {},
            },
        )
        existing_keys.add(f"dimension:{key}")
        result.persisted.append(AcceptPersisted(sid, "dimension", str(row.id), key))

    def _create_relationship(self, version_id, ws, proj, payload, existing_keys, sid, result):
        key = str(payload.get("key") or "").strip()
        if not key:
            return
        if f"relationship:{key}" in existing_keys:
            result.conflicts.append(AcceptConflict(sid, "duplicate", f"Relationship `{key}` already exists."))
            return
        join_expression = payload.get("join_expression")
        if not join_expression:
            from_field = payload.get("from_field") or "id"
            to_field = payload.get("to_field") or "id"
            join_expression = f"{payload.get('from_entity_key')}.{from_field} = {payload.get('to_entity_key')}.{to_field}"
        row = self._registry.create_relationship(
            version_id,
            workspace_id=ws,
            project_id=proj,
            data={
                "key": key,
                "name": payload.get("name") or key,
                "from_entity_key": payload.get("from_entity_key"),
                "to_entity_key": payload.get("to_entity_key"),
                "join_expression": join_expression,
                "relationship_type": payload.get("relationship_type") or "many_to_one",
                "description": payload.get("description"),
            },
        )
        existing_keys.add(f"relationship:{key}")
        result.persisted.append(AcceptPersisted(sid, "relationship", str(row.id), key))

    def _create_term(self, version_id, ws, proj, payload, existing_keys, sid, result):
        key = str(payload.get("key") or payload.get("term") or "").strip()
        term = str(payload.get("term") or payload.get("name") or key).strip()
        if not key:
            key = re.sub(r"[^a-zA-Z0-9]+", "_", term.lower()).strip("_")[:64]
        if f"term:{key}" in existing_keys:
            result.conflicts.append(AcceptConflict(sid, "duplicate", f"Glossary term `{term}` already exists."))
            return
        row = self._registry.create_term(
            version_id,
            workspace_id=ws,
            project_id=proj,
            data={
                "key": key,
                "term": term,
                "definition": payload.get("definition") or term,
                "synonyms": payload.get("synonyms") or [],
                "related_entity_keys": list(payload.get("related_entity_keys") or []),
                "related_metric_keys": list(payload.get("related_metric_keys") or []),
                "related_dimension_keys": list(payload.get("related_dimension_keys") or []),
            },
        )
        existing_keys.add(f"term:{key}")
        result.persisted.append(AcceptPersisted(sid, "term", str(row.id), key))

    def _count_objects(self, version_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, int]:
        return {
            "entities": len(self._registry.list_entities(version_id, workspace_id=workspace_id, project_id=project_id)),
            "metrics": len(self._registry.list_metrics(version_id, workspace_id=workspace_id, project_id=project_id)),
            "dimensions": len(self._registry.list_dimensions(version_id, workspace_id=workspace_id, project_id=project_id)),
            "relationships": len(self._registry.list_relationships(version_id, workspace_id=workspace_id, project_id=project_id)),
            "terms": len(self._registry.list_terms(version_id, workspace_id=workspace_id, project_id=project_id)),
        }
