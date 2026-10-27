from __future__ import annotations

import uuid
from dataclasses import dataclass, field

VALIDATOR_VERSION = "s3.0"

READINESS_NOT_READY = "NOT_READY"
READINESS_WITH_WARNINGS = "READY_WITH_WARNINGS"
READINESS_READY = "READY"

BREAKING = "BREAKING"
POTENTIALLY_BREAKING = "POTENTIALLY_BREAKING"
NON_BREAKING = "NON_BREAKING"


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str  # ERROR | WARNING | INFO
    category: str = "STRUCTURE"
    object_type: str | None = None
    object_key: str | None = None
    remediation: str | None = None
    metadata: dict = field(default_factory=dict)
    path: str | None = None
    id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "category": self.category,
            "object_type": self.object_type,
            "object_key": self.object_key,
            "remediation": self.remediation,
            "metadata": self.metadata,
            "path": self.path,
        }


@dataclass
class ValidationSummary:
    valid: bool
    activation_ready: bool
    readiness: str
    readiness_score: int
    error_count: int
    warning_count: int
    info_count: int
    checks_run: int
    checks_skipped: int
    duration_ms: int
    stages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "activation_ready": self.activation_ready,
            "readiness": self.readiness,
            "readiness_score": self.readiness_score,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "checks_run": self.checks_run,
            "checks_skipped": self.checks_skipped,
            "duration_ms": self.duration_ms,
            "stages": self.stages,
        }


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    info: list[ValidationIssue] = field(default_factory=list)
    summary: ValidationSummary | None = None
    run_id: str | None = None
    issues_by_category: dict[str, list[dict]] = field(default_factory=dict)
    connection_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        legacy_errors = [i for i in self.errors]
        legacy_warnings = [i for i in self.warnings]
        payload = {
            "valid": self.valid,
            "errors": [e.to_dict() for e in legacy_errors],
            "warnings": [w.to_dict() for w in legacy_warnings],
            "info": [i.to_dict() for i in self.info],
            "issues_by_category": self.issues_by_category,
            "connection_status": self.connection_status,
            "run_id": self.run_id,
        }
        if self.summary:
            payload["summary"] = self.summary.to_dict()
            payload["readiness"] = self.summary.readiness
            payload["activation_ready"] = self.summary.activation_ready
            payload["readiness_score"] = self.summary.readiness_score
        return payload


def new_issue_id() -> str:
    return str(uuid.uuid4())
