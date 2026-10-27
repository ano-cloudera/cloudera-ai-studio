from __future__ import annotations

from dataclasses import dataclass

from app.db.platform_models import SemanticModelRow, SemanticVersionRow
from app.semantic_registry.governance_types import ValidationIssue, ValidationResult, ValidationSummary

__all__ = [
    "ValidationIssue",
    "ValidationResult",
    "ValidationSummary",
    "ResolvedSemantic",
    "RuntimeArtifact",
]


@dataclass
class ResolvedSemantic:
    model: SemanticModelRow
    version: SemanticVersionRow


@dataclass
class RuntimeArtifact:
    adapter: str
    version: str
    uri: str | None
    checksum: str
    content_preview: str
    content: str
    metadata: dict
