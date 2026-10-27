from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.semantic_registry.governance_pipeline import SemanticGovernancePipeline
from app.semantic_registry.types import ValidationResult


class SemanticValidationService:
    """Facade for semantic validation (S3 governance pipeline)."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._pipeline = SemanticGovernancePipeline(session)

    def validate_version(
        self,
        version_id: uuid.UUID,
        *,
        mode: str = "full",
        source_mode: str | None = None,
        persist: bool = True,
        created_by: str | None = None,
    ) -> ValidationResult:
        return self._pipeline.validate_version(
            version_id,
            mode=mode,
            source_mode=source_mode,
            persist=persist,
            created_by=created_by,
        )
