from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass(frozen=True)
class DatasourceExecutionContext:
    legacy_fallback: bool
    connector_id: uuid.UUID | None = None
    connector_type: str | None = None
    connector_name: str | None = None
    dialect: str = "hive"
    semantic_version_id: uuid.UUID | None = None
    semantic_entity_keys: tuple[str, ...] = ()
    qualified_sources: dict[str, str] = field(default_factory=dict)
    allowed_physical_tables: frozenset[str] = frozenset()

    def to_dict(self) -> dict[str, Any]:
        return {
            "legacy_fallback": self.legacy_fallback,
            "connector_id": str(self.connector_id) if self.connector_id else None,
            "connector_type": self.connector_type,
            "connector_name": self.connector_name,
            "dialect": self.dialect,
            "semantic_version_id": str(self.semantic_version_id) if self.semantic_version_id else None,
            "semantic_entity_keys": list(self.semantic_entity_keys),
            "qualified_sources": dict(self.qualified_sources),
            "allowed_physical_tables": sorted(self.allowed_physical_tables),
        }

    @staticmethod
    def from_dict(raw: dict[str, Any] | None) -> DatasourceExecutionContext | None:
        if not raw:
            return None
        cid = raw.get("connector_id")
        vid = raw.get("semantic_version_id")
        return DatasourceExecutionContext(
            legacy_fallback=bool(raw.get("legacy_fallback")),
            connector_id=uuid.UUID(str(cid)) if cid else None,
            connector_type=raw.get("connector_type"),
            connector_name=raw.get("connector_name"),
            dialect=str(raw.get("dialect") or "hive"),
            semantic_version_id=uuid.UUID(str(vid)) if vid else None,
            semantic_entity_keys=tuple(raw.get("semantic_entity_keys") or ()),
            qualified_sources=dict(raw.get("qualified_sources") or {}),
            allowed_physical_tables=frozenset(raw.get("allowed_physical_tables") or ()),
        )


@dataclass(frozen=True)
class DatasourceRoutingError:
    code: str
    message: str
    safe_message: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "safe_message": self.safe_message}
