from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from time import perf_counter

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.platform_models import (
    SemanticDimensionRow,
    SemanticEntityRow,
    SemanticMetricRow,
    SemanticModelRow,
    SemanticRelationshipRow,
    SemanticTermRow,
    SemanticTestCaseRow,
    SemanticValidationIssueRow,
    SemanticValidationRunRow,
    SemanticVersionRow,
)
from app.semantic_registry.connector_resolver import ConnectorMetadataResolver
from app.semantic_registry.governance_types import (
    READINESS_NOT_READY,
    READINESS_READY,
    READINESS_WITH_WARNINGS,
    VALIDATOR_VERSION,
    ValidationIssue,
    ValidationResult,
    ValidationSummary,
    new_issue_id,
)
from app.semantic_registry.runtime_adapter import OssieRuntimeAdapter
from app.semantic_registry.source_validators import (
    ImpalaSemanticSourceValidator,
    TrinoSemanticSourceValidator,
    extract_identifier_candidates,
    get_source_validator,
)
from app.semantic_registry.sql_guard import assert_read_only_sql

_AGGREGATIONS = {"sum", "avg", "count", "min", "max"}


class SemanticGovernancePipeline:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._settings = get_settings()

    def validate_version(
        self,
        version_id: uuid.UUID,
        *,
        mode: str = "full",
        source_mode: str | None = None,
        persist: bool = True,
        created_by: str | None = None,
    ) -> ValidationResult:
        started = perf_counter()
        source_mode = source_mode or self._settings.semantic_source_validation_mode
        version = self._session.get(SemanticVersionRow, version_id)
        if not version:
            issue = ValidationIssue("not_found", "Semantic version not found", "ERROR", category="STRUCTURE")
            return ValidationResult(valid=False, errors=[issue])

        run = SemanticValidationRunRow(
            semantic_version_id=version_id,
            status="RUNNING",
            mode=mode,
            validator_version=VALIDATOR_VERSION,
            created_by=created_by,
            summary={},
        )
        if persist:
            self._session.add(run)
            self._session.flush()

        issues: list[ValidationIssue] = []
        stages: list[str] = []
        checks_run = 0
        checks_skipped = 0

        entities = self._load_entities(version_id)
        metrics = self._load_metrics(version_id)
        dimensions = self._load_dimensions(version_id)
        relationships = self._load_relationships(version_id)
        terms = self._load_terms(version_id)
        test_cases = self._load_test_cases(version_id)

        connection_status = {
            "impala": ImpalaSemanticSourceValidator(self._settings).health()[0],
            "trino": TrinoSemanticSourceValidator(self._settings).health()[0],
        }

        def add(issue: ValidationIssue) -> None:
            issue.id = new_issue_id()
            issues.append(issue)

        if mode in {"structural", "full"}:
            stages.append("structural")
            checks_run += self._validate_structural(
                version, entities, metrics, dimensions, relationships, terms, add
            )

        if mode in {"source", "full"}:
            stages.append("source")
            run_src, skip_src = self._validate_sources(
                version_id, entities, metrics, dimensions, relationships, source_mode, add
            )
            checks_run += run_src
            checks_skipped += skip_src

        if mode == "full":
            stages.append("semantic")
            checks_run += self._validate_semantic(metrics, dimensions, relationships, terms, entities, add)
            stages.append("artifact")
            checks_run += self._validate_artifact(version_id, entities, metrics, dimensions, relationships, add)
            stages.append("test_cases")
            checks_run += self._validate_test_cases(test_cases, metrics, dimensions, entities, add)

        errors = [i for i in issues if i.severity == "ERROR"]
        warnings = [i for i in issues if i.severity == "WARNING"]
        info = [i for i in issues if i.severity == "INFO"]

        readiness, activation_ready, score = self._readiness(errors, warnings, checks_skipped)
        duration_ms = int((perf_counter() - started) * 1000)
        summary = ValidationSummary(
            valid=len(errors) == 0,
            activation_ready=activation_ready,
            readiness=readiness,
            readiness_score=score,
            error_count=len(errors),
            warning_count=len(warnings),
            info_count=len(info),
            checks_run=checks_run,
            checks_skipped=checks_skipped,
            duration_ms=duration_ms,
            stages=stages,
        )

        by_category: dict[str, list[dict]] = {}
        for issue in issues:
            by_category.setdefault(issue.category, []).append(issue.to_dict())

        result = ValidationResult(
            valid=summary.valid,
            errors=errors,
            warnings=warnings,
            info=info,
            summary=summary,
            run_id=str(run.id) if persist else None,
            issues_by_category=by_category,
            connection_status=connection_status,
        )

        if persist:
            run.status = "COMPLETED" if summary.valid else "FAILED"
            run.completed_at = datetime.now(timezone.utc)
            run.summary = summary.to_dict()
            for issue in issues:
                self._session.add(
                    SemanticValidationIssueRow(
                        validation_run_id=run.id,
                        severity=issue.severity,
                        category=issue.category,
                        object_type=issue.object_type,
                        object_key=issue.object_key,
                        code=issue.code,
                        message=issue.message,
                        remediation=issue.remediation,
                        metadata_=issue.metadata,
                    )
                )
            version.last_validation_run_id = run.id
            version.activation_readiness = readiness
            version.validated_at = run.completed_at
            self._session.flush()

        return result

    def _readiness(self, errors: list, warnings: list, skipped: int) -> tuple[str, bool, int]:
        if errors:
            score = max(0, 100 - len(errors) * 15 - len(warnings) * 3)
            return READINESS_NOT_READY, False, score
        if warnings:
            score = max(40, 100 - len(warnings) * 5 - skipped * 2)
            return READINESS_WITH_WARNINGS, True, score
        score = max(60, 100 - skipped * 2)
        return READINESS_READY, True, score

    def _validate_structural(
        self,
        version: SemanticVersionRow,
        entities,
        metrics,
        dimensions,
        relationships,
        terms,
        add,
    ) -> int:
        checks = 0
        entity_keys = {e.key for e in entities}
        metric_keys = {m.key for m in metrics}
        dimension_keys = {d.key for d in dimensions}

        for collection, label in (
            (entities, "entity"),
            (metrics, "metric"),
            (dimensions, "dimension"),
            (relationships, "relationship"),
            (terms, "term"),
        ):
            seen: set[str] = set()
            for row in collection:
                checks += 1
                if row.key in seen:
                    add(
                        ValidationIssue(
                            "duplicate_key",
                            f"Duplicate {label} key: {row.key}",
                            "ERROR",
                            category="STRUCTURE",
                            object_type=label,
                            object_key=row.key,
                            remediation=f"Rename or remove duplicate {label} key.",
                        )
                    )
                seen.add(row.key)

        for entity in entities:
            checks += 1
            if entity.source_type not in {"impala", "trino", "logical", "postgres"}:
                add(
                    ValidationIssue(
                        "invalid_source_type",
                        f"Invalid source_type on {entity.key}",
                        "ERROR",
                        category="STRUCTURE",
                        object_type="entity",
                        object_key=entity.key,
                    )
                )
            if entity.source_type in {"impala", "trino", "postgres"} and not (entity.table_name or entity.view_name):
                if not entity.schema and not entity.table_name:
                    add(
                        ValidationIssue(
                            "insufficient_physical_metadata",
                            f"Entity {entity.key} lacks schema/table metadata",
                            "ERROR",
                            category="STRUCTURE",
                            object_type="entity",
                            object_key=entity.key,
                        )
                    )

        for metric in metrics:
            checks += 1
            if not metric.expression.strip():
                add(
                    ValidationIssue(
                        "missing_field",
                        f"Metric {metric.key} missing expression",
                        "ERROR",
                        category="METRIC",
                        object_type="metric",
                        object_key=metric.key,
                    )
                )
            if metric.source_entity_key not in entity_keys:
                add(
                    ValidationIssue(
                        "missing_entity",
                        f"Metric {metric.key} references unknown entity {metric.source_entity_key}",
                        "ERROR",
                        category="METRIC",
                        object_type="metric",
                        object_key=metric.key,
                    )
                )

        for dim in dimensions:
            checks += 1
            if dim.source_entity_key not in entity_keys:
                add(
                    ValidationIssue(
                        "missing_entity",
                        f"Dimension {dim.key} references unknown entity {dim.source_entity_key}",
                        "ERROR",
                        category="DIMENSION",
                        object_type="dimension",
                        object_key=dim.key,
                    )
                )
            if not dim.source_column.strip():
                add(
                    ValidationIssue(
                        "missing_field",
                        f"Dimension {dim.key} missing source_column",
                        "ERROR",
                        category="DIMENSION",
                        object_type="dimension",
                        object_key=dim.key,
                    )
                )
            if not (dim.description or "").strip():
                add(
                    ValidationIssue(
                        "missing_description",
                        f"Dimension {dim.key} has no business description",
                        "WARNING",
                        category="DIMENSION",
                        object_type="dimension",
                        object_key=dim.key,
                    )
                )

        for rel in relationships:
            checks += 1
            if rel.from_entity_key not in entity_keys or rel.to_entity_key not in entity_keys:
                add(
                    ValidationIssue(
                        "missing_entity",
                        f"Relationship {rel.key} references unknown entity",
                        "ERROR",
                        category="RELATIONSHIP",
                        object_type="relationship",
                        object_key=rel.key,
                    )
                )
            if not rel.join_expression.strip():
                add(
                    ValidationIssue(
                        "missing_join",
                        f"Relationship {rel.key} missing join_expression",
                        "ERROR",
                        category="RELATIONSHIP",
                        object_type="relationship",
                        object_key=rel.key,
                    )
                )
            if rel.relationship_type not in {"many_to_one", "one_to_many", "many_to_many", "one_to_one"}:
                add(
                    ValidationIssue(
                        "invalid_relationship_type",
                        f"Relationship {rel.key} has invalid relationship_type",
                        "WARNING",
                        category="RELATIONSHIP",
                        object_type="relationship",
                        object_key=rel.key,
                    )
                )

        for term in terms:
            checks += 1
            for mk in term.related_metric_keys or []:
                if mk not in metric_keys:
                    add(
                        ValidationIssue(
                            "missing_metric_ref",
                            f"Term {term.key} references unknown metric {mk}",
                            "ERROR",
                            category="GLOSSARY",
                            object_type="term",
                            object_key=term.key,
                        )
                    )
            for dk in term.related_dimension_keys or []:
                if dk not in dimension_keys:
                    add(
                        ValidationIssue(
                            "missing_dimension_ref",
                            f"Term {term.key} references unknown dimension {dk}",
                            "ERROR",
                            category="GLOSSARY",
                            object_type="term",
                            object_key=term.key,
                        )
                    )

        if version.status == "ACTIVE":
            others = self._session.execute(
                select(SemanticVersionRow).where(
                    SemanticVersionRow.semantic_model_id == version.semantic_model_id,
                    SemanticVersionRow.status == "ACTIVE",
                    SemanticVersionRow.id != version.id,
                )
            ).scalars().all()
            if others:
                add(
                    ValidationIssue(
                        "multiple_active",
                        "More than one ACTIVE version on semantic model",
                        "ERROR",
                        category="STRUCTURE",
                    )
                )
        return checks

    def _project_context(self, version_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
        version = self._session.get(SemanticVersionRow, version_id)
        if not version:
            raise ValueError("version not found")
        model = self._session.get(SemanticModelRow, version.semantic_model_id)
        if not model:
            raise ValueError("model not found")
        return model.workspace_id, model.project_id

    def _validate_sources(
        self, version_id, entities, metrics, dimensions, relationships, source_mode, add
    ) -> tuple[int, int]:
        checks = 0
        skipped = 0
        entity_map = {e.key: e for e in entities}
        column_cache: dict[str, dict] = {}
        normalized_cache: dict[str, dict[str, str]] = {}
        workspace_id, project_id = self._project_context(version_id)
        connector_resolver = ConnectorMetadataResolver(self._session, settings=self._settings)

        def columns_for(entity: SemanticEntityRow) -> dict:
            nonlocal checks, skipped
            if entity.key in column_cache:
                return column_cache[entity.key]
            if entity.connection_id:
                resolved = connector_resolver.load_columns_for_entity(
                    entity, workspace_id=workspace_id, project_id=project_id
                )
                checks += 1
                if resolved.message == "CONNECTOR_DISABLED":
                    add(
                        ValidationIssue(
                            "CONNECTOR_DISABLED",
                            f"Entity `{entity.key}` connector is disabled.",
                            "ERROR",
                            category="SOURCE",
                            object_type="entity",
                            object_key=entity.key,
                        )
                    )
                    column_cache[entity.key] = {}
                    return {}
                if not resolved.ok or not resolved.columns:
                    add(
                        ValidationIssue(
                            "source_table_missing",
                            f"Entity `{entity.key}` source not reachable: {resolved.message}",
                            "ERROR",
                            category="SOURCE",
                            object_type="entity",
                            object_key=entity.key,
                            remediation="Verify connector, catalog/schema/table and connection test.",
                        )
                    )
                    column_cache[entity.key] = {}
                    return {}
                column_cache[entity.key] = resolved.columns
                if resolved.normalized_by_column:
                    normalized_cache[entity.key] = resolved.normalized_by_column
                return resolved.columns

            validator = get_source_validator(entity.source_type)
            if not validator:
                column_cache[entity.key] = {}
                return {}
            table = entity.table_name or entity.view_name or ""
            result = validator.load_columns(catalog=entity.catalog, schema=entity.schema, table=table)
            checks += 1
            if result.skipped:
                skipped += 1
                add(
                    ValidationIssue(
                        "source_check_skipped",
                        result.message or f"Source checks skipped for entity {entity.key}",
                        "INFO",
                        category="SOURCE",
                        object_type="entity",
                        object_key=entity.key,
                    )
                )
                column_cache[entity.key] = {}
                return {}
            if not result.ok:
                add(
                    ValidationIssue(
                        "source_table_missing",
                        f"Entity `{entity.key}` source not reachable: {result.message}",
                        "ERROR",
                        category="SOURCE",
                        object_type="entity",
                        object_key=entity.key,
                        remediation="Verify catalog/schema/table and connection.",
                    )
                )
                column_cache[entity.key] = {}
                return {}
            column_cache[entity.key] = result.columns
            return result.columns

        for entity in entities:
            if entity.source_type == "logical":
                continue
            table = entity.table_name or entity.view_name or ""
            if entity.source_type in ("postgres", "trino", "impala") and not entity.connection_id:
                checks += 1
                add(
                    ValidationIssue(
                        "missing_connector_binding",
                        f"Entity `{entity.key}` requires a connector binding for source type `{entity.source_type}`.",
                        "ERROR",
                        category="SOURCE",
                        object_type="entity",
                        object_key=entity.key,
                    )
                )
                continue
            if entity.connection_id:
                exists = connector_resolver.table_exists_for_entity(
                    entity, workspace_id=workspace_id, project_id=project_id
                )
                checks += 1
                if exists.message == "CONNECTOR_DISABLED":
                    add(
                        ValidationIssue(
                            "CONNECTOR_DISABLED",
                            f"Entity `{entity.key}` connector is disabled.",
                            "ERROR",
                            category="SOURCE",
                            object_type="entity",
                            object_key=entity.key,
                        )
                    )
                    continue
                if not exists.ok:
                    add(
                        ValidationIssue(
                            "source_table_missing",
                            f"Entity `{entity.key}` table/view not found: {exists.message}",
                            "ERROR",
                            category="SOURCE",
                            object_type="entity",
                            object_key=entity.key,
                        )
                    )
                    continue
            else:
                validator = get_source_validator(entity.source_type)
                if not validator:
                    continue
                exists = validator.table_exists(catalog=entity.catalog, schema=entity.schema, table=table)
                checks += 1
                if exists.skipped:
                    skipped += 1
                    continue
                if not exists.ok:
                    add(
                        ValidationIssue(
                            "source_table_missing",
                            f"Entity `{entity.key}` table/view not found: {exists.message}",
                            "ERROR",
                            category="SOURCE",
                            object_type="entity",
                            object_key=entity.key,
                        )
                    )
                    continue
            cols = columns_for(entity)
            if entity.primary_key:
                for pk_col in [c.strip() for c in entity.primary_key.split(",") if c.strip()]:
                    checks += 1
                    if cols and pk_col.lower() not in cols:
                        add(
                            ValidationIssue(
                                "missing_column",
                                f"Entity `{entity.key}` primary key column `{pk_col}` not found in source table.",
                                "ERROR",
                                category="SOURCE",
                                object_type="entity",
                                object_key=entity.key,
                            )
                        )

        for dim in dimensions:
            entity = entity_map.get(dim.source_entity_key)
            if not entity or entity.source_type == "logical":
                continue
            cols = columns_for(entity)
            checks += 1
            if cols and dim.source_column.lower() not in cols:
                add(
                    ValidationIssue(
                        "missing_column",
                        f"Dimension `{dim.key}` column `{dim.source_column}` not found on entity `{entity.key}`.",
                        "ERROR",
                        category="SOURCE",
                        object_type="dimension",
                        object_key=dim.key,
                    )
                )
            norm_map = normalized_cache.get(entity.key) or {}
            stored_norm = (dim.metadata_ or {}).get("normalized_type")
            current_norm = norm_map.get(dim.source_column.lower())
            if stored_norm and current_norm and str(stored_norm).upper() != str(current_norm).upper():
                checks += 1
                add(
                    ValidationIssue(
                        "source_type_drift",
                        f"Dimension `{dim.key}` column `{dim.source_column}` type changed ({stored_norm} → {current_norm}).",
                        "WARNING",
                        category="SOURCE",
                        object_type="dimension",
                        object_key=dim.key,
                    )
                )

        for metric in metrics:
            entity = entity_map.get(metric.source_entity_key)
            if not entity or entity.source_type == "logical":
                continue
            cols = columns_for(entity)
            for ident in extract_identifier_candidates(metric.expression):
                checks += 1
                if cols and ident not in cols and ident not in _AGGREGATIONS:
                    add(
                        ValidationIssue(
                            "metric_column_unresolved",
                            f"Metric `{metric.key}` expression references unknown column `{ident}`.",
                            "WARNING",
                            category="METRIC",
                            object_type="metric",
                            object_key=metric.key,
                        )
                    )
            if source_mode == "safe_query" and entity.source_type in ("impala", "trino", "postgres"):
                if entity.connection_id:
                    from app.ask_data.physical_identifiers import qualified_physical_name
                    from app.connectors.factory import ConnectorFactory
                    from app.connectors.sql_safety import assert_connector_readonly_sql
                    from app.semantic_registry.connector_reference import validate_entity_connector

                    conn = validate_entity_connector(
                        self._session,
                        connection_id=entity.connection_id,
                        workspace_id=workspace_id,
                        project_id=project_id,
                        require_enabled=False,
                    )
                    checks += 1
                    if not conn:
                        continue
                    try:
                        qual = qualified_physical_name(
                            connector_type=conn.connector_type,
                            catalog=entity.catalog,
                            schema=entity.schema,
                            table_name=entity.table_name,
                            view_name=entity.view_name,
                        )
                        sql = f"SELECT {metric.expression} AS m FROM {qual} d"
                        assert_connector_readonly_sql(f"{sql} LIMIT 0")
                        adapter = ConnectorFactory(settings=self._settings).create(
                            conn.connector_type,
                            dict(conn.config or {}),
                            secret_ref=conn.secret_ref,
                        )
                        adapter.execute_readonly_query(f"{sql} LIMIT 0", max_rows=0)
                        probe_ok = True
                        probe_msg = None
                    except Exception as exc:
                        probe_ok = False
                        probe_msg = str(exc)
                    if not probe_ok:
                        add(
                            ValidationIssue(
                                "metric_probe_failed",
                                f"Metric `{metric.key}` safe probe failed: {probe_msg}",
                                "WARNING",
                                category="METRIC",
                                object_type="metric",
                                object_key=metric.key,
                            )
                        )
                elif entity.source_type == "impala":
                    table = entity.table_name or entity.view_name or ""
                    qual = ".".join(p for p in (entity.schema, table) if p)
                    sql = f"SELECT {metric.expression} AS m FROM {qual}"
                    validator = get_source_validator(entity.source_type)
                    if validator:
                        probe = validator.validate_limit_zero(sql)
                        checks += 1
                        if not probe.ok and not probe.skipped:
                            add(
                                ValidationIssue(
                                    "metric_probe_failed",
                                    f"Metric `{metric.key}` safe probe failed: {probe.message}",
                                    "WARNING",
                                    category="METRIC",
                                    object_type="metric",
                                    object_key=metric.key,
                                )
                            )

        for rel in relationships:
            left_ent = entity_map.get(rel.from_entity_key)
            right_ent = entity_map.get(rel.to_entity_key)
            if (
                left_ent
                and right_ent
                and left_ent.connection_id
                and right_ent.connection_id
                and left_ent.connection_id != right_ent.connection_id
            ):
                checks += 1
                add(
                    ValidationIssue(
                        "CROSS_CONNECTOR_RELATIONSHIP_UNSUPPORTED",
                        f"Relationship `{rel.key}` spans different connectors; cross-connector joins are not supported.",
                        "ERROR",
                        category="RELATIONSHIP",
                        object_type="relationship",
                        object_key=rel.key,
                    )
                )
                continue
            entity_keys = {rel.from_entity_key, rel.to_entity_key}
            join_alias_stop = {"a", "b"}
            for key in (rel.from_entity_key, rel.to_entity_key):
                entity = entity_map.get(key)
                if not entity or entity.source_type == "logical":
                    continue
                cols = columns_for(entity)
                for ident in extract_identifier_candidates(rel.join_expression):
                    if ident in join_alias_stop or ident in entity_keys:
                        continue
                    checks += 1
                    if cols and ident not in cols:
                        add(
                            ValidationIssue(
                                "join_column_missing",
                                f"Relationship `{rel.key}` join references missing column `{ident}` on `{key}`.",
                                "ERROR",
                                category="RELATIONSHIP",
                                object_type="relationship",
                                object_key=rel.key,
                            )
                        )
            if source_mode == "safe_query":
                left = entity_map.get(rel.from_entity_key)
                right = entity_map.get(rel.to_entity_key)
                if left and right and left.source_type != "logical":
                    lt = left.table_name or left.view_name
                    rt = right.table_name or right.view_name
                    lq = ".".join(p for p in (left.schema, lt) if p)
                    rq = ".".join(p for p in (right.schema, rt) if p)
                    sql = f"SELECT 1 FROM {lq} a {rel.join_type.upper()} JOIN {rq} b ON {rel.join_expression} LIMIT 0"
                    validator = get_source_validator(left.source_type)
                    if validator:
                        try:
                            assert_read_only_sql(sql)
                            probe = validator.validate_limit_zero(sql)
                            checks += 1
                            if not probe.ok and not probe.skipped:
                                add(
                                    ValidationIssue(
                                        "join_probe_failed",
                                        f"Relationship `{rel.key}` join probe failed: {probe.message}",
                                        "WARNING",
                                        category="RELATIONSHIP",
                                        object_type="relationship",
                                        object_key=rel.key,
                                    )
                                )
                        except ValueError as exc:
                            add(
                                ValidationIssue(
                                    "unsafe_join_sql",
                                    str(exc),
                                    "ERROR",
                                    category="RELATIONSHIP",
                                    object_type="relationship",
                                    object_key=rel.key,
                                )
                            )
        return checks, skipped

    def _validate_semantic(self, metrics, dimensions, relationships, terms, entities, add) -> int:
        checks = 0
        synonym_to_metrics: dict[str, set[str]] = {}

        for metric in metrics:
            checks += 1
            if metric.aggregation and metric.aggregation.lower() not in _AGGREGATIONS:
                add(
                    ValidationIssue(
                        "invalid_aggregation",
                        f"Metric `{metric.key}` has unsupported aggregation `{metric.aggregation}`.",
                        "ERROR",
                        category="METRIC",
                        object_type="metric",
                        object_key=metric.key,
                    )
                )
            if not (metric.business_definition or "").strip():
                add(
                    ValidationIssue(
                        "missing_business_definition",
                        f"Metric `{metric.key}` has no business_definition",
                        "WARNING",
                        category="METRIC",
                        object_type="metric",
                        object_key=metric.key,
                    )
                )
            meta = metric.metadata_ or {}
            tests = meta.get("test_cases") or meta.get("tests") or []
            if isinstance(tests, dict):
                tests = [tests]
            for test in tests:
                checks += 1
                if test.get("expected_min") is not None and test.get("expected_max") is not None:
                    if test["expected_min"] > test["expected_max"]:
                        add(
                            ValidationIssue(
                                "invalid_metric_test",
                                f"Metric `{metric.key}` test case min > max",
                                "WARNING",
                                category="METRIC",
                                object_type="metric",
                                object_key=metric.key,
                            )
                        )
            for syn in [metric.name, *(metric.synonyms or [])]:
                synonym_to_metrics.setdefault(syn.strip().lower(), set()).add(metric.key)

        for term in terms:
            for syn in [term.term, *(term.synonyms or [])]:
                key = syn.strip().lower()
                if not key:
                    continue
                for mk in term.related_metric_keys or []:
                    synonym_to_metrics.setdefault(key, set()).add(mk)

        term_keys: dict[str, list[str]] = {}
        for term in terms:
            checks += 1
            term_keys.setdefault(term.term.strip().lower(), []).append(term.key)
            for syn in term.synonyms or []:
                term_keys.setdefault(syn.strip().lower(), []).append(term.key)

        for syn, keys in term_keys.items():
            if len(set(keys)) > 1:
                add(
                    ValidationIssue(
                        "duplicate_term",
                        f"Glossary synonym `{syn}` used by multiple terms.",
                        "WARNING",
                        category="GLOSSARY",
                        object_type="term",
                        metadata={"term_keys": list(set(keys))},
                    )
                )

        for syn, metric_keys in synonym_to_metrics.items():
            if len(metric_keys) > 1:
                add(
                    ValidationIssue(
                        "AMBIGUOUS_TERM",
                        f"`{syn}` maps to multiple metrics: {', '.join(sorted(metric_keys))}.",
                        "WARNING",
                        category="GLOSSARY",
                        remediation="Clarify glossary mapping or disambiguate synonyms.",
                        metadata={"metric_keys": sorted(metric_keys)},
                    )
                )
        return checks

    def _validate_artifact(self, version_id, entities, metrics, dimensions, relationships, add) -> int:
        checks = 0
        try:
            adapter = OssieRuntimeAdapter()
            a1 = adapter.generate_artifact(self._session, version_id, write_file=False)
            a2 = adapter.generate_artifact(self._session, version_id, write_file=False)
            checks += 2
            # Parse the full document: `content_preview` is cut at 8000 characters and a model with
            # enough metrics would then fail with a ScannerError in the middle of a word.
            parsed = yaml.safe_load(a1.content or a1.content_preview)
            if not isinstance(parsed, dict):
                add(
                    ValidationIssue(
                        "artifact_invalid",
                        "Generated OSSIE YAML root is not a mapping",
                        "ERROR",
                        category="ARTIFACT",
                    )
                )
            if a1.checksum != a2.checksum:
                add(
                    ValidationIssue(
                        "artifact_non_deterministic",
                        "Artifact checksum differs between consecutive generations",
                        "WARNING",
                        category="ARTIFACT",
                    )
                )
            meta = a1.metadata or {}
            for label, reg_count in (
                ("entities", len(entities)),
                ("metrics", len(metrics)),
                ("dimensions", len(dimensions)),
                ("relationships", len(relationships)),
            ):
                checks += 1
                art_count = int(meta.get(label, meta.get(f"{label.rstrip('s')}_count", 0)))
                if art_count < reg_count:
                    add(
                        ValidationIssue(
                            "artifact_count_mismatch",
                            f"Artifact missing {label}: registry={reg_count} artifact={art_count}",
                            "ERROR",
                            category="ARTIFACT",
                            remediation="Review runtime adapter serialization.",
                        )
                    )
        except Exception as exc:
            add(
                ValidationIssue(
                    "artifact_generation_failed",
                    f"Runtime artifact generation failed: {type(exc).__name__}: {exc}",
                    "ERROR",
                    category="ARTIFACT",
                )
            )
        return checks

    def _validate_test_cases(self, test_cases, metrics, dimensions, entities, add) -> int:
        checks = 0
        metric_keys = {m.key for m in metrics}
        dimension_keys = {d.key for d in dimensions}
        entity_keys = {e.key for e in entities}
        for tc in test_cases:
            if not tc.enabled:
                continue
            checks += 1
            for mk in tc.expected_metric_keys or []:
                if mk not in metric_keys:
                    add(
                        ValidationIssue(
                            "test_case_missing_metric",
                            f"Test `{tc.name}` expects unknown metric `{mk}`",
                            "WARNING",
                            category="RUNTIME_READINESS",
                            object_type="test_case",
                            object_key=tc.name,
                        )
                    )
            for dk in tc.expected_dimension_keys or []:
                if dk not in dimension_keys:
                    add(
                        ValidationIssue(
                            "test_case_missing_dimension",
                            f"Test `{tc.name}` expects unknown dimension `{dk}`",
                            "WARNING",
                            category="RUNTIME_READINESS",
                            object_type="test_case",
                            object_key=tc.name,
                        )
                    )
            for ek in tc.expected_entity_keys or []:
                if ek not in entity_keys:
                    add(
                        ValidationIssue(
                            "test_case_missing_entity",
                            f"Test `{tc.name}` expects unknown entity `{ek}`",
                            "WARNING",
                            category="RUNTIME_READINESS",
                            object_type="test_case",
                            object_key=tc.name,
                        )
                    )
            add(
                ValidationIssue(
                    "test_query_plan",
                    f"Test query `{tc.name}`: {tc.question[:120]}",
                    "INFO",
                    category="RUNTIME_READINESS",
                    object_type="test_case",
                    object_key=tc.name,
                    metadata={
                        "expected_metrics": tc.expected_metric_keys,
                        "expected_dimensions": tc.expected_dimension_keys,
                    },
                )
            )
        return checks

    def _load_entities(self, version_id: uuid.UUID):
        return list(
            self._session.execute(select(SemanticEntityRow).where(SemanticEntityRow.semantic_version_id == version_id)).scalars()
        )

    def _load_metrics(self, version_id: uuid.UUID):
        return list(
            self._session.execute(select(SemanticMetricRow).where(SemanticMetricRow.semantic_version_id == version_id)).scalars()
        )

    def _load_dimensions(self, version_id: uuid.UUID):
        return list(
            self._session.execute(select(SemanticDimensionRow).where(SemanticDimensionRow.semantic_version_id == version_id)).scalars()
        )

    def _load_relationships(self, version_id: uuid.UUID):
        return list(
            self._session.execute(
                select(SemanticRelationshipRow).where(SemanticRelationshipRow.semantic_version_id == version_id)
            ).scalars()
        )

    def _load_terms(self, version_id: uuid.UUID):
        return list(
            self._session.execute(select(SemanticTermRow).where(SemanticTermRow.semantic_version_id == version_id)).scalars()
        )

    def _load_test_cases(self, version_id: uuid.UUID):
        return list(
            self._session.execute(select(SemanticTestCaseRow).where(SemanticTestCaseRow.semantic_version_id == version_id)).scalars()
        )
