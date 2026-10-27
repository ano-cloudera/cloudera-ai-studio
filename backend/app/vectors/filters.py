from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorSearchFilters:
    workspace_id: str
    project_id: str
    library_ids: tuple[str, ...] | None = None
    document_ids: tuple[str, ...] | None = None

    def validate_scoped(self) -> None:
        if not self.workspace_id or not self.project_id:
            raise ValueError("workspace_id and project_id are required for scoped retrieval")


def build_qdrant_filter(filters: VectorSearchFilters):
    from qdrant_client.http import models as qmodels

    filters.validate_scoped()
    must: list = [
        qmodels.FieldCondition(key="workspace_id", match=qmodels.MatchValue(value=filters.workspace_id)),
        qmodels.FieldCondition(key="project_id", match=qmodels.MatchValue(value=filters.project_id)),
    ]
    if filters.library_ids:
        must.append(
            qmodels.FieldCondition(
                key="library_id",
                match=qmodels.MatchAny(any=list(filters.library_ids)),
            )
        )
    if filters.document_ids:
        must.append(
            qmodels.FieldCondition(
                key="document_id",
                match=qmodels.MatchAny(any=list(filters.document_ids)),
            )
        )
    return qmodels.Filter(must=must)
