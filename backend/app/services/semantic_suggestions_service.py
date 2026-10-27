"""Deterministic (+ optional LLM) semantic modeling suggestions for V2 wizard."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.connectors.service import ConnectorRegistryService
from app.core.config import Settings, get_settings
from app.semantic_registry.connector_resolver import ConnectorMetadataResolver


@dataclass
class SuggestedEntity:
    key: str
    name: str
    description: str | None
    connection_id: str
    catalog: str | None
    schema: str | None
    table_name: str
    primary_key: str | None
    status: str = "suggested"

    def to_dict(self) -> dict:
        return {
            "suggestion_id": f"entity:{self.key}",
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "connection_id": self.connection_id,
            "catalog": self.catalog,
            "schema": self.schema,
            "table_name": self.table_name,
            "primary_key": self.primary_key,
            "status": self.status,
        }


@dataclass
class SemanticSuggestionsResult:
    entities: list[SuggestedEntity] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    dimensions: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    glossary_suggestions: list[dict] = field(default_factory=list)
    provider: str = "deterministic"

    def to_dict(self) -> dict:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "metrics": self.metrics,
            "dimensions": self.dimensions,
            "relationships": self.relationships,
            "glossary_suggestions": self.glossary_suggestions,
            "provider": self.provider,
        }


_NUMERIC = re.compile(r"(amount|total|qty|quantity|price|revenue|sales|cost|count|value|rate)", re.I)
_DATE = re.compile(r"(date|time|month|year|day|timestamp|created|updated)", re.I)
_ID = re.compile(r"(_id$|^id$|_key$|^key$)", re.I)


def _slug(text: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return base[:64] or "item"


class SemanticSuggestionsService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._connectors = ConnectorRegistryService(session, settings=self._settings)
        self._metadata = ConnectorMetadataResolver(session, settings=self._settings)

    def suggest(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        connection_id: uuid.UUID,
        tables: list[str],
    ) -> SemanticSuggestionsResult:
        self._connectors.get_connector(connection_id, workspace_id=workspace_id, project_id=project_id)
        result = SemanticSuggestionsResult()
        table_entities: dict[str, SuggestedEntity] = {}

        for raw in tables[:50]:
            qualified = raw.strip()
            if not qualified:
                continue
            parts = qualified.split(".")
            catalog = parts[0] if len(parts) == 3 else None
            schema = parts[-2] if len(parts) >= 2 else None
            table_name = parts[-1]
            entity_key = _slug(table_name)
            entity = SuggestedEntity(
                key=entity_key,
                name=table_name.replace("_", " ").title(),
                description=f"Suggested business object from {qualified}",
                connection_id=str(connection_id),
                catalog=catalog,
                schema=schema,
                table_name=table_name,
                primary_key=None,
            )
            table_entities[qualified] = entity
            result.entities.append(entity)

            columns: list[dict] = []
            try:
                detail = self._metadata.describe_table(
                    connection_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    catalog=catalog,
                    schema=schema,
                    table=table_name,
                )
                columns = [{"name": c.name, "data_type": c.native_type or c.data_type} for c in detail.columns]
            except Exception:
                columns = []

            pk_candidates = [c for c in columns if _ID.search(c.get("name", ""))]
            if pk_candidates:
                entity.primary_key = pk_candidates[0]["name"]

            for col in columns[:200]:
                name = col.get("name") or ""
                dtype = (col.get("data_type") or col.get("type") or "").lower()
                if _DATE.search(name) or "date" in dtype or "time" in dtype:
                    dim_key = _slug(f"{entity_key}_{name}")
                    result.dimensions.append(
                        {
                            "suggestion_id": f"dimension:{dim_key}",
                            "key": dim_key,
                            "name": name.replace("_", " ").title(),
                            "source_entity_key": entity_key,
                            "source_column": name,
                            "category": "TIME",
                            "status": "suggested",
                        }
                    )
                elif _NUMERIC.search(name) or any(t in dtype for t in ("int", "decimal", "double", "float", "numeric")):
                    met_key = _slug(f"{entity_key}_{name}_total")
                    result.metrics.append(
                        {
                            "suggestion_id": f"metric:{met_key}",
                            "key": met_key,
                            "name": f"Total {name.replace('_', ' ').title()}",
                            "expression": f"SUM({entity_key}.{name})",
                            "source_entity_key": entity_key,
                            "status": "suggested",
                        }
                    )
                elif "char" in dtype or "text" in dtype or "string" in dtype:
                    dim_key = _slug(f"{entity_key}_{name}")
                    result.dimensions.append(
                        {
                            "suggestion_id": f"dimension:{dim_key}",
                            "key": dim_key,
                            "name": name.replace("_", " ").title(),
                            "source_entity_key": entity_key,
                            "source_column": name,
                            "category": "ATTRIBUTE",
                            "status": "suggested",
                        }
                    )

        # FK-style relationship hints: col ending _id on table A matching pk on table B
        for qualified, ent in table_entities.items():
            try:
                detail = self._metadata.describe_table(
                    connection_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    catalog=ent.catalog,
                    schema=ent.schema,
                    table=ent.table_name,
                )
                cols = [{"name": c.name, "data_type": c.native_type or c.data_type} for c in detail.columns]
            except Exception:
                continue
            for col in cols:
                cname = col.get("name") or ""
                if not cname.endswith("_id") or cname == ent.primary_key:
                    continue
                base = cname[:-3]
                for other_q, other in table_entities.items():
                    if other.key == ent.key:
                        continue
                    if other.table_name == base or other.key == _slug(base):
                        rel_key = _slug(f"{ent.key}_to_{other.key}")
                        result.relationships.append(
                            {
                                "suggestion_id": f"relationship:{rel_key}",
                                "key": rel_key,
                                "name": f"{ent.name} → {other.name}",
                                "from_entity_key": ent.key,
                                "to_entity_key": other.key,
                                "join_expression": f"{ent.key}.{cname} = {other.key}.{other.primary_key or cname}",
                                "relationship_type": "many_to_one",
                                "status": "suggested",
                            }
                        )

        return result
