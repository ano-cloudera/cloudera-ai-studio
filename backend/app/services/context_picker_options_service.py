"""Unified @ context picker options (DATA, SEMANTIC, KNOWLEDGE)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ask_data.table_context_id import encode_raw_table_id
from app.connectors.discovery import MetadataDiscoveryService
from app.connectors.service import ConnectorRegistryService
from app.core.config import get_settings
from app.db.platform_models import LibraryRow, SemanticEntityRow, SemanticMetricRow, SemanticModelRow, SemanticVersionRow
from app.services.library_service import LibraryService


class ContextPickerOptionsService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._settings = get_settings()

    def list_options(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        search: str | None = None,
        limit: int = 100,
    ) -> dict:
        needle = (search or "").strip().lower()
        limit = max(1, min(limit, 200))

        knowledge = self._knowledge(workspace_id, project_id, needle, limit)
        semantic = self._semantic(workspace_id, project_id, needle, limit)
        data = self._tables(workspace_id, project_id, needle, limit)

        return {
            "groups": [
                {"id": "data", "label": "Data", "options": data},
                {"id": "semantic", "label": "Semantic", "options": semantic},
                {"id": "knowledge", "label": "Knowledge", "options": knowledge},
            ]
        }

    def _knowledge(self, workspace_id: uuid.UUID, project_id: uuid.UUID, needle: str, limit: int) -> list[dict]:
        svc = LibraryService(self._session)
        page = svc.list_libraries_paginated(
            workspace_id=workspace_id,
            project_id=project_id,
            page=1,
            page_size=limit,
            search=needle or None,
            sort="updated_at",
            order="desc",
        )
        rows = page.items
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "type": "knowledge_library",
                    "id": str(row.id),
                    "name": row.name,
                    "subtitle": f"{row.document_count or 0} documents",
                    "group": "knowledge",
                }
            )
        return out

    def _semantic(self, workspace_id: uuid.UUID, project_id: uuid.UUID, needle: str, limit: int) -> list[dict]:
        models = list(
            self._session.execute(
                select(SemanticModelRow).where(
                    SemanticModelRow.workspace_id == workspace_id,
                    SemanticModelRow.project_id == project_id,
                )
            ).scalars()
        )
        out: list[dict] = []
        for model in models:
            if needle and needle not in model.name.lower() and needle not in model.key.lower():
                continue
            active_vid = model.active_version_id
            status = "Draft"
            if active_vid:
                ver = self._session.get(SemanticVersionRow, active_vid)
                if ver and ver.status == "ACTIVE":
                    status = "Published"
            out.append(
                {
                    "type": "semantic_model",
                    "id": str(model.id),
                    "name": model.name,
                    "subtitle": status,
                    "group": "semantic",
                    "metadata": {"model_key": model.key},
                }
            )
            if len(out) >= limit:
                break

            if not active_vid:
                continue
            metrics = list(
                self._session.execute(
                    select(SemanticMetricRow).where(SemanticMetricRow.semantic_version_id == active_vid).limit(50)
                ).scalars()
            )
            for metric in metrics:
                hay = f"{metric.name} {metric.key} {' '.join(metric.synonyms or [])}".lower()
                if needle and needle not in hay:
                    continue
                out.append(
                    {
                        "type": "semantic_metric",
                        "id": str(metric.id),
                        "name": metric.name,
                        "subtitle": model.name,
                        "group": "semantic",
                        "metadata": {"model_id": str(model.id), "metric_key": metric.key},
                    }
                )
                if len(out) >= limit:
                    return out

            entities = list(
                self._session.execute(
                    select(SemanticEntityRow).where(SemanticEntityRow.semantic_version_id == active_vid).limit(50)
                ).scalars()
            )
            for ent in entities:
                hay = f"{ent.name} {ent.key} {ent.table_name or ''}".lower()
                if needle and needle not in hay:
                    continue
                out.append(
                    {
                        "type": "semantic_entity",
                        "id": str(ent.id),
                        "name": ent.name,
                        "subtitle": model.name,
                        "group": "semantic",
                        "metadata": {"model_id": str(model.id), "entity_key": ent.key},
                    }
                )
                if len(out) >= limit:
                    return out
        return out[:limit]

    def _tables(self, workspace_id: uuid.UUID, project_id: uuid.UUID, needle: str, limit: int) -> list[dict]:
        registry = ConnectorRegistryService(self._session, settings=self._settings)
        discovery = MetadataDiscoveryService(registry, settings=self._settings)
        seen: set[str] = set()
        out: list[dict] = []

        for connector in registry.list_connectors(workspace_id=workspace_id, project_id=project_id, enabled=True):
            try:
                payload = discovery.list_tables(
                    connector.id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    search=needle or None,
                    limit=min(limit * 2, 200),
                )
            except Exception:
                continue
            for row in payload.get("tables") or []:
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                schema = row.get("schema")
                catalog = row.get("catalog")
                label = ".".join(p for p in (schema, name) if p)
                if needle and needle not in label.casefold() and needle not in name.casefold():
                    continue
                stable = encode_raw_table_id(
                    connector_id=connector.id,
                    catalog=catalog,
                    schema=schema,
                    table=name,
                )
                if stable in seen:
                    continue
                seen.add(stable)
                out.append(
                    {
                        "type": "table",
                        "id": stable,
                        "name": label or name,
                        "subtitle": connector.name,
                        "group": "data",
                        "metadata": {
                            "connector_id": str(connector.id),
                            "connector_type": connector.connector_type,
                            "catalog": catalog,
                            "schema": schema,
                            "table": name,
                        },
                    }
                )
                if len(out) >= limit:
                    return out

        if len(out) < limit:
            version_ids = select(SemanticVersionRow.id).join(
                SemanticModelRow,
                SemanticVersionRow.semantic_model_id == SemanticModelRow.id,
            ).where(
                SemanticModelRow.workspace_id == workspace_id,
                SemanticModelRow.project_id == project_id,
            )
            entities = list(
                self._session.execute(
                    select(SemanticEntityRow)
                    .where(
                        SemanticEntityRow.semantic_version_id.in_(version_ids),
                        SemanticEntityRow.connection_id.isnot(None),
                    )
                    .limit(limit * 3)
                ).scalars()
            )
            for ent in entities:
                parts = [ent.catalog, ent.schema, ent.table_name or ent.view_name]
                label = ".".join(p for p in parts if p)
                if not label or label in seen:
                    continue
                if needle and needle not in label.lower() and needle not in ent.name.lower():
                    continue
                if ent.connection_id and (ent.table_name or ent.view_name):
                    stable = encode_raw_table_id(
                        connector_id=ent.connection_id,
                        catalog=ent.catalog,
                        schema=ent.schema,
                        table=(ent.table_name or ent.view_name or "").strip(),
                    )
                else:
                    stable = str(ent.id)
                if stable in seen:
                    continue
                seen.add(stable)
                out.append(
                    {
                        "type": "table",
                        "id": stable,
                        "name": label,
                        "subtitle": ent.name,
                        "group": "data",
                        "metadata": {
                            "connection_id": str(ent.connection_id) if ent.connection_id else None,
                            "entity_id": str(ent.id),
                        },
                    }
                )
                if len(out) >= limit:
                    break
        return out
