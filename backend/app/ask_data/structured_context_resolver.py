"""Resolve explicit / automatic structured Ask Data context with deterministic precedence."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ask_data.datasource_router import AskDataDatasourceRouter
from app.ask_data.raw_table_companion import expand_raw_table_context
from app.ask_data.table_context_id import RawTableRef, decode_raw_table_id, encode_raw_table_id
from app.ask_data.types import DatasourceExecutionContext, DatasourceRoutingError
from app.connectors.discovery import MetadataDiscoveryService
from app.connectors.service import ConnectorRegistryService
from app.core.config import Settings
from app.core.models import AskDataRequest, ChatContextSource
from app.db.platform_models import (
    SemanticEntityRow,
    SemanticMetricRow,
    SemanticModelRow,
    SemanticTermRow,
    SemanticVersionRow,
    WorkspaceRow,
)
from app.workspace.ask_data_settings import read_ask_data_settings
from app.semantic.context import SemanticContextService
from app.semantic_runtime.loader import RuntimeContextBundle, SemanticRuntimeLoader


@dataclass(frozen=True)
class ClarificationPayload:
    reason: str
    message: str
    options: list[dict[str, str]]


def _normalize_metric_token(raw: str) -> str:
    token = str(raw or "").strip()
    if token.casefold().startswith("suggested metric "):
        token = token[17:].strip()
    return token


def _metric_display_name(metric: SemanticMetricRow) -> str:
    from app.ask_data.metric_labels import humanize_metric_label

    return humanize_metric_label(
        name=metric.key or metric.name,
        definition={
            "display_name": metric.name,
            "description": metric.business_definition or metric.description,
        },
    )


def _rank_metrics_for_question(metrics: list[SemanticMetricRow], question: str) -> list[SemanticMetricRow]:
    q = question.casefold()
    scored: list[tuple[int, SemanticMetricRow]] = []
    for metric in metrics:
        score = 0
        blob = " ".join(
            filter(None, [metric.name, metric.key, getattr(metric, "business_definition", None)])
        ).casefold()
        if "customer" in q or "nasabah" in q:
            if "customer" in blob:
                score += 80
        if "transaksi" in q or "transaction" in q:
            if "transaction" in blob:
                score += 80
        if any(t in q for t in ("trend", "pertumbuhan", "per bulan", "bulanan", "12 bulan")):
            if "transaction" in blob:
                score += 60
            if "transaction_id" in blob:
                score += 50
        if any(t in q for t in ("jumlah", "banyak", "count")) and ("transaksi" in q or "transaction" in q):
            if "transaction_id" in blob:
                score += 100
            if "amount" in blob:
                score -= 30
        if score <= 0:
            score = 1
        scored.append((score, metric))
    scored.sort(key=lambda item: (-item[0], (item[1].name or "").casefold()))
    return [row for _, row in scored]


def _model_metric_clarification(
    session: Session,
    model: SemanticModelRow,
    ctx: SemanticContextService,
    question: str,
) -> ClarificationPayload | None:
    if model.active_version_id:
        rows = list(
            session.execute(
                select(SemanticMetricRow).where(SemanticMetricRow.semantic_version_id == model.active_version_id)
            ).scalars()
        )
        ranked = _rank_metrics_for_question(rows, question)[:4]
        options = [
            {"type": "semantic_metric", "id": str(metric.id), "name": _metric_display_name(metric)}
            for metric in ranked
        ]
        if options:
            return ClarificationPayload(
                reason="metric_ambiguous",
                message="Metrik mana yang ingin Anda lihat? Pilih salah satu metric yang dipublish di semantic model ini.",
                options=options,
            )
    raw = ctx.registry._metric_picker_clarification(question)
    return _clarification_from_resolution(_map_picker_options_to_db_metrics(session, model, raw))


def _map_picker_options_to_db_metrics(
    session: Session,
    model: SemanticModelRow,
    resolution: dict[str, Any],
) -> dict[str, Any]:
    if not model.active_version_id or resolution.get("status") != "needs_clarification":
        return resolution
    rows = list(
        session.execute(
            select(SemanticMetricRow).where(SemanticMetricRow.semantic_version_id == model.active_version_id)
        ).scalars()
    )
    by_key = {str(m.key or "").strip(): m for m in rows if m.key}
    by_name = {str(m.name or "").strip(): m for m in rows if m.name}
    options = resolution.get("options")
    if not isinstance(options, list):
        return resolution
    mapped: list[dict[str, str]] = []
    for item in options:
        if not isinstance(item, dict):
            continue
        raw_id = _normalize_metric_token(str(item.get("id") or ""))
        raw_name = _normalize_metric_token(str(item.get("name") or ""))
        row = (
            by_key.get(raw_id)
            or by_name.get(raw_id)
            or by_key.get(raw_name)
            or by_name.get(raw_name)
            or by_name.get(str(item.get("name") or "").strip())
        )
        if row is None:
            continue
        mapped.append(
            {
                "type": "semantic_metric",
                "id": str(row.id),
                "name": _metric_display_name(row),
            }
        )
    if not mapped:
        return resolution
    out = dict(resolution)
    out["options"] = mapped
    out["question"] = "Metrik mana yang ingin Anda lihat? Pilih salah satu metric yang dipublish di semantic model ini."
    return out


def _clarification_from_resolution(resolution: dict[str, Any]) -> ClarificationPayload | None:
    if resolution.get("status") != "needs_clarification":
        return None
    raw_options = resolution.get("options")
    if not isinstance(raw_options, list) or not raw_options:
        return None
    options: list[dict[str, str]] = []
    for item in raw_options:
        if not isinstance(item, dict):
            continue
        opt_id = str(item.get("id") or "").strip()
        if not opt_id:
            continue
        options.append(
            {
                "type": str(item.get("type") or "semantic_metric"),
                "id": opt_id,
                "name": str(item.get("name") or opt_id),
            }
        )
    if not options:
        return None
    return ClarificationPayload(
        reason=str(resolution.get("reason") or "metric_ambiguous"),
        message=str(
            resolution.get("question")
            or "Which metric would you like to report on?"
        ),
        options=options,
    )


@dataclass
class StructuredAskPrecedence:
    force_ossie: bool
    skip_auto_semantic_when_explicit: bool
    resolution: dict[str, Any] | None
    clarification: ClarificationPayload | None
    explicit_error: str | None
    runtime_bundle: RuntimeContextBundle | None
    context_mode: str | None


def resolve_structured_ask(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    request: AskDataRequest,
    semantic_context: SemanticContextService,
    question: str,
    session_analysis_context: dict[str, Any] | None = None,
) -> StructuredAskPrecedence:
    from app.chat.context_sources import structured_data_sources

    structured = structured_data_sources(request.context_sources)
    if len(structured) > 1:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Only one structured @ context is supported per Ask Data request.",
            runtime_bundle=None,
            context_mode=None,
        )
    if len(structured) == 1:
        return _resolve_explicit(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            source=structured[0],
            semantic_context=semantic_context,
            question=question,
        )
    auto_semantic = _resolve_automatic_semantic_model(
        session,
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id,
        question=question,
        session_analysis_context=session_analysis_context,
    )
    if auto_semantic.clarification or auto_semantic.resolution or auto_semantic.explicit_error:
        return auto_semantic
    auto = _resolve_automatic_table(session, settings=settings, workspace_id=workspace_id, project_id=project_id, question=question)
    if auto.clarification or auto.resolution or auto.explicit_error:
        return auto
    return StructuredAskPrecedence(
        force_ossie=False,
        skip_auto_semantic_when_explicit=False,
        resolution=None,
        clarification=None,
        explicit_error=None,
        runtime_bundle=None,
        context_mode=None,
    )


def _resolve_explicit(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    source: ChatContextSource,
    semantic_context: SemanticContextService,
    question: str,
) -> StructuredAskPrecedence:
    if source.type == "table":
        return _resolve_explicit_table(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            source=source,
            question=question,
        )
    if source.type == "semantic_metric":
        return _resolve_explicit_metric(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            source=source,
            semantic_context=semantic_context,
            question=question,
        )
    if source.type == "semantic_model":
        return _resolve_explicit_model(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            source=source,
            semantic_context=semantic_context,
            question=question,
        )
    if source.type == "semantic_entity":
        return _resolve_explicit_entity(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            source=source,
            semantic_context=semantic_context,
            question=question,
        )
    if source.type == "semantic_term":
        return _resolve_explicit_term(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            source=source,
            semantic_context=semantic_context,
            question=question,
        )
    return StructuredAskPrecedence(
        force_ossie=True,
        skip_auto_semantic_when_explicit=True,
        resolution=None,
        clarification=None,
        explicit_error=f"Unsupported structured context type: {source.type}",
        runtime_bundle=None,
        context_mode=None,
    )


def _resolve_explicit_table(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    source: ChatContextSource,
    question: str,
) -> StructuredAskPrecedence:
    ref = decode_raw_table_id(source.id)
    entity: SemanticEntityRow | None = None
    if ref is None:
        try:
            ent_id = uuid.UUID(source.id)
        except ValueError:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=None,
                explicit_error="Table context id is not valid for this project.",
                runtime_bundle=None,
                context_mode=None,
            )
        entity = session.get(SemanticEntityRow, ent_id)
        if entity is None:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=None,
                explicit_error="Selected table context was not found.",
                runtime_bundle=None,
                context_mode=None,
            )
        version = session.get(SemanticVersionRow, entity.semantic_version_id)
        model = session.get(SemanticModelRow, version.semantic_model_id) if version else None
        if not model or model.workspace_id != workspace_id or model.project_id != project_id:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=None,
                explicit_error="Selected table is not accessible in this project.",
                runtime_bundle=None,
                context_mode=None,
            )
        if entity.connection_id is None:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=None,
                explicit_error="Selected table is not linked to a connector.",
                runtime_bundle=None,
                context_mode=None,
            )
        ref = RawTableRef(
            connector_id=entity.connection_id,
            catalog=entity.catalog,
            schema=entity.schema,
            table=(entity.table_name or entity.view_name or "").strip(),
        )

    built = _raw_table_resolution(
        session,
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id,
        ref=ref,
        question=question,
        display_name=source.name or ref.table,
    )
    if isinstance(built, str):
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error=built,
            runtime_bundle=None,
            context_mode=None,
        )
    return StructuredAskPrecedence(
        force_ossie=True,
        skip_auto_semantic_when_explicit=True,
        resolution=built,
        clarification=None,
        explicit_error=None,
        runtime_bundle=None,
        context_mode="RAW_TABLE",
    )


def _raw_table_resolution(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    ref: RawTableRef,
    question: str,
    display_name: str,
) -> dict[str, Any] | str:
    router = AskDataDatasourceRouter(session, settings=settings)
    routing = router.resolve_raw_table(
        workspace_id=workspace_id,
        project_id=project_id,
        connector_id=ref.connector_id,
        catalog=ref.catalog,
        schema=ref.schema,
        table=ref.table,
    )
    if isinstance(routing, DatasourceRoutingError):
        return routing.safe_message
    discovery = MetadataDiscoveryService(ConnectorRegistryService(session, settings=settings), settings=settings)
    try:
        detail = discovery.describe_table(
            ref.connector_id,
            workspace_id=workspace_id,
            project_id=project_id,
            catalog=ref.catalog,
            schema=ref.schema,
            table=ref.table,
        )
        columns = [c.name for c in detail.columns if c.name]
    except Exception:
        columns = []
    qualified = next(iter(routing.qualified_sources.values()), ref.table)
    allowed_keys, raw_policy = expand_raw_table_context(
        session,
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id,
        ref=ref,
        question=question,
        primary_qualified=qualified,
        primary_columns=columns,
    )
    routing_dict = routing.to_dict()
    if len(allowed_keys) > 1:
        routing_dict["allowed_physical_tables"] = sorted(allowed_keys)
    return {
        "status": "raw_table",
        "context_mode": "RAW_TABLE",
        "explicit_structured": True,
        "question": question,
        "raw_table": {
            "connector_id": str(ref.connector_id),
            "catalog": ref.catalog,
            "schema": ref.schema,
            "table": ref.table,
            "qualified_name": qualified,
            "display_name": display_name,
            "column_names": columns,
            "stable_id": encode_raw_table_id(
                connector_id=ref.connector_id,
                catalog=ref.catalog,
                schema=ref.schema,
                table=ref.table,
            ),
        },
        "datasource_context": routing_dict,
        "raw_table_policy": raw_policy,
    }


def _resolve_explicit_metric(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    source: ChatContextSource,
    semantic_context: SemanticContextService,
    question: str,
) -> StructuredAskPrecedence:
    metric: SemanticMetricRow | None = None
    lookup = _normalize_metric_token(source.id)
    try:
        metric_id = uuid.UUID(source.id)
        metric = session.get(SemanticMetricRow, metric_id)
    except ValueError:
        metric = session.execute(
            select(SemanticMetricRow).where(
                (SemanticMetricRow.key == lookup)
                | (SemanticMetricRow.name == lookup)
                | (SemanticMetricRow.key == source.id)
                | (SemanticMetricRow.name == source.id)
            )
        ).scalar_one_or_none()
        if metric is None:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=None,
                explicit_error="Metric context id is not valid.",
                runtime_bundle=None,
                context_mode=None,
            )
    if metric is None:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected metric was not found.",
            runtime_bundle=None,
            context_mode=None,
        )
    version = session.get(SemanticVersionRow, metric.semantic_version_id)
    model = session.get(SemanticModelRow, version.semantic_model_id) if version else None
    if not model or model.workspace_id != workspace_id or model.project_id != project_id:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected metric is not accessible in this project.",
            runtime_bundle=None,
            context_mode=None,
        )
    bundle = SemanticRuntimeLoader.get(settings).load_from_session(
        session,
        workspace_id=workspace_id,
        project_id=project_id,
        model_key=model.key,
    )
    if bundle.mode != "runtime" and not model.active_version_id:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected metric is not published to Ask Data for this model.",
            runtime_bundle=None,
            context_mode=None,
        )
    ctx = bundle.context
    metric_key = _resolve_registry_metric_key(ctx, metric)
    if not metric_key:
        hit = ctx.registry.resolve_metric(metric.name or metric.key)
        if hit.get("status") == "resolved" and hit.get("metric"):
            metric_key = str(hit["metric"])
    if not metric_key:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected metric is not available in the active semantic runtime.",
            runtime_bundle=None,
            context_mode=None,
        )
    try:
        definition = ctx.metric_definition(metric_key)
    except Exception:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected metric is not available in the active semantic runtime.",
            runtime_bundle=None,
            context_mode=None,
        )
    resolution: dict[str, Any] = {
        "status": "resolved",
        "metric": metric_key,
        "matched_alias": "explicit_structured_metric",
        "definition": definition,
        "dimensions": [],
        "dimension_mismatch": [],
        "explicit_structured": True,
        "context_mode": "GOVERNED_SEMANTIC",
    }
    if getattr(ctx, "_registry_runtime", False):
        from app.ask_data.intent_satisfaction import validate_registry_resolution

        validation = validate_registry_resolution(question, resolution, definition=definition, registry=ctx.registry)
        resolution["intent_validation"] = validation.as_metadata()
        if not validation.intent_complete:
            resolution = {
                "status": "needs_clarification",
                "question": validation.user_message,
                "reason": validation.reason_code,
                "metric": metric_key,
                "definition": definition,
                "explicit_structured": True,
                "context_mode": "GOVERNED_SEMANTIC",
                "intent_validation": validation.as_metadata(),
            }
    return StructuredAskPrecedence(
        force_ossie=True,
        skip_auto_semantic_when_explicit=True,
        resolution=resolution,
        clarification=None,
        explicit_error=None,
        runtime_bundle=bundle,
        context_mode="GOVERNED_SEMANTIC",
    )


def _resolve_explicit_model(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    source: ChatContextSource,
    semantic_context: SemanticContextService,
    question: str,
    session_analysis_context: dict[str, Any] | None = None,
    auto_attached: bool = False,
) -> StructuredAskPrecedence:
    try:
        model_id = uuid.UUID(source.id)
    except ValueError:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Semantic model context id is not valid.",
            runtime_bundle=None,
            context_mode=None,
        )
    model = session.get(SemanticModelRow, model_id)
    if not model or model.workspace_id != workspace_id or model.project_id != project_id:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected semantic model was not found in this project.",
            runtime_bundle=None,
            context_mode=None,
        )
    bundle = SemanticRuntimeLoader.get(settings).load_from_session(
        session,
        workspace_id=workspace_id,
        project_id=project_id,
        model_key=model.key,
    )
    if bundle.mode != "runtime":
        message = (
            "Selected semantic model is not active on Ask Data. "
            "Use Publish to Ask Data in Semantic Layer, confirm Deployment details shows ACTIVE, "
            "then restart the backend."
        )
        if not model.active_version_id:
            message = "Selected semantic model is not published to Ask Data."
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error=message,
            runtime_bundle=None,
            context_mode=None,
        )
    from app.services.conversational import _is_capability_meta_question

    if _is_capability_meta_question(question):
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error=None,
            runtime_bundle=bundle,
            context_mode="GOVERNED_SEMANTIC",
        )
    ctx = bundle.context
    resolution = ctx.resolve(question, session_analysis_context=session_analysis_context)
    resolution = {
        **resolution,
        "explicit_structured": not auto_attached,
        "context_mode": "GOVERNED_SEMANTIC",
        "semantic_model_id": str(model.id),
    }
    if auto_attached:
        resolution["matched_alias"] = resolution.get("matched_alias") or "auto_semantic_model"
    if resolution.get("status") == "resolved":
        metric = str(resolution.get("metric") or "")
        if metric:
            try:
                resolution.setdefault("definition", ctx.metric_definition(metric))
            except Exception:
                return StructuredAskPrecedence(
                    force_ossie=True,
                    skip_auto_semantic_when_explicit=True,
                    resolution=None,
                    clarification=None,
                    explicit_error="Could not resolve a governed metric for the selected semantic model.",
                    runtime_bundle=None,
                    context_mode=None,
                )
    elif resolution.get("status") == "unsupported":
        metric_clarification = _model_metric_clarification(session, model, ctx, question)
        if metric_clarification:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=metric_clarification,
                explicit_error=None,
                runtime_bundle=bundle,
                context_mode="GOVERNED_SEMANTIC",
            )
        if _is_capability_meta_question(question):
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=None,
                explicit_error=None,
                runtime_bundle=bundle,
                context_mode="GOVERNED_SEMANTIC",
            )
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error=str(resolution.get("question") or "Question could not be resolved against the selected semantic model."),
            runtime_bundle=None,
            context_mode=None,
        )
    elif resolution.get("status") not in {"needs_clarification", "fallback"}:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error=str(resolution.get("question") or "Question could not be resolved against the selected semantic model."),
            runtime_bundle=None,
            context_mode=None,
        )
    if resolution.get("status") == "needs_clarification":
        resolution = _map_picker_options_to_db_metrics(session, model, resolution)
        metric_clarification = _clarification_from_resolution(resolution) or _model_metric_clarification(
            session, model, ctx, question
        )
        if metric_clarification:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=metric_clarification,
                explicit_error=None,
                runtime_bundle=bundle,
                context_mode="GOVERNED_SEMANTIC",
            )
    return StructuredAskPrecedence(
        force_ossie=True,
        skip_auto_semantic_when_explicit=True,
        resolution=resolution,
        clarification=None,
        explicit_error=None,
        runtime_bundle=bundle,
        context_mode="GOVERNED_SEMANTIC",
    )


def _resolve_explicit_term(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    source: ChatContextSource,
    semantic_context: SemanticContextService,
    question: str,
) -> StructuredAskPrecedence:
    try:
        term_id = uuid.UUID(source.id)
    except ValueError:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Glossary term context id is not valid.",
            runtime_bundle=None,
            context_mode=None,
        )
    term = session.get(SemanticTermRow, term_id)
    if not term:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected glossary term was not found.",
            runtime_bundle=None,
            context_mode=None,
        )
    version = session.get(SemanticVersionRow, term.semantic_version_id)
    model = session.get(SemanticModelRow, version.semantic_model_id) if version else None
    if not model or model.workspace_id != workspace_id or model.project_id != project_id:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected glossary term is not accessible in this project.",
            runtime_bundle=None,
            context_mode=None,
        )
    bundle = SemanticRuntimeLoader.get(settings).load_from_session(
        session,
        workspace_id=workspace_id,
        project_id=project_id,
        model_key=model.key,
    )
    if bundle.mode != "runtime":
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Semantic model for this term is not published to Ask Data.",
            runtime_bundle=None,
            context_mode=None,
        )
    ctx = bundle.context
    metric_key: str | None = None
    for raw in list(term.related_metric_keys or []):
        candidate = str(raw).strip()
        if candidate and candidate in ctx.registry.metrics:
            metric_key = candidate
            break
    if metric_key is None:
        for raw in list(term.related_metric_keys or []):
            candidate = str(raw).strip().casefold()
            for reg_key in ctx.registry.metrics:
                if reg_key.casefold() == candidate:
                    metric_key = reg_key
                    break
            if metric_key:
                break
    if metric_key:
        try:
            definition = ctx.metric_definition(metric_key)
        except Exception:
            definition = None
        if definition:
            resolution: dict[str, Any] = {
                "status": "resolved",
                "metric": metric_key,
                "matched_alias": "explicit_glossary_term",
                "definition": definition,
                "dimensions": [],
                "dimension_mismatch": [],
                "explicit_structured": True,
                "context_mode": "GOVERNED_SEMANTIC",
                "semantic_model_id": str(model.id),
                "glossary_term": {
                    "key": term.key,
                    "term": term.term,
                    "definition": term.definition,
                },
            }
            dims = [str(d) for d in (term.related_dimension_keys or []) if str(d).strip()]
            allowed = set(definition.get("allowed_dimensions") or [])
            resolution["dimensions"] = [d for d in dims if d in allowed]
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=resolution,
                clarification=None,
                explicit_error=None,
                runtime_bundle=bundle,
                context_mode="GOVERNED_SEMANTIC",
            )
    model_prec = _resolve_explicit_model(
        session,
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id,
        source=ChatContextSource(type="semantic_model", id=str(model.id), name=model.name),
        semantic_context=semantic_context,
        question=question,
    )
    glossary_meta = {"key": term.key, "term": term.term, "definition": term.definition}
    if model_prec.resolution is not None:
        return StructuredAskPrecedence(
            force_ossie=model_prec.force_ossie,
            skip_auto_semantic_when_explicit=model_prec.skip_auto_semantic_when_explicit,
            resolution={**model_prec.resolution, "glossary_term": glossary_meta},
            clarification=model_prec.clarification,
            explicit_error=model_prec.explicit_error,
            runtime_bundle=model_prec.runtime_bundle,
            context_mode=model_prec.context_mode,
        )
    return model_prec


def _resolve_explicit_entity(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    source: ChatContextSource,
    semantic_context: SemanticContextService,
    question: str,
) -> StructuredAskPrecedence:
    try:
        ent_id = uuid.UUID(source.id)
    except ValueError:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Semantic entity context id is not valid.",
            runtime_bundle=None,
            context_mode=None,
        )
    entity = session.get(SemanticEntityRow, ent_id)
    if entity is None:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected semantic entity was not found.",
            runtime_bundle=None,
            context_mode=None,
        )
    version = session.get(SemanticVersionRow, entity.semantic_version_id)
    model = session.get(SemanticModelRow, version.semantic_model_id) if version else None
    if not model or model.workspace_id != workspace_id or model.project_id != project_id:
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=None,
            clarification=None,
            explicit_error="Selected semantic entity is not accessible in this project.",
            runtime_bundle=None,
            context_mode=None,
        )
    if entity.connection_id:
        ref = RawTableRef(
            connector_id=entity.connection_id,
            catalog=entity.catalog,
            schema=entity.schema,
            table=(entity.table_name or entity.view_name or "").strip(),
        )
        built = _raw_table_resolution(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            ref=ref,
            question=question,
            display_name=source.name or entity.name,
        )
        if isinstance(built, str):
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=True,
                resolution=None,
                clarification=None,
                explicit_error=built,
                runtime_bundle=None,
                context_mode=None,
            )
        built["context_mode"] = "RAW_TABLE"
        built["semantic_entity_id"] = str(entity.id)
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=True,
            resolution=built,
            clarification=None,
            explicit_error=None,
            runtime_bundle=None,
            context_mode="RAW_TABLE",
        )
    return _resolve_explicit_model(
        session,
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id,
        source=ChatContextSource(type="semantic_model", id=str(model.id), name=model.name),
        semantic_context=semantic_context,
        question=question,
    )


def _published_models_for_project(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[SemanticModelRow]:
    rows = list(
        session.execute(
            select(SemanticModelRow).where(
                SemanticModelRow.workspace_id == workspace_id,
                SemanticModelRow.project_id == project_id,
                SemanticModelRow.active_version_id.isnot(None),
            )
        ).scalars()
    )
    return rows


def _resolve_automatic_semantic_model(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    question: str,
    session_analysis_context: dict[str, Any] | None = None,
) -> StructuredAskPrecedence:
    from app.services.conversational import _is_capability_meta_question

    if _is_capability_meta_question(question):
        return StructuredAskPrecedence(
            force_ossie=False,
            skip_auto_semantic_when_explicit=False,
            resolution=None,
            clarification=None,
            explicit_error=None,
            runtime_bundle=None,
            context_mode=None,
        )
    workspace = session.get(WorkspaceRow, workspace_id)
    ask_settings = read_ask_data_settings(workspace.settings_json if workspace else None)
    if not ask_settings.auto_attach_semantic_model:
        return StructuredAskPrecedence(
            force_ossie=False,
            skip_auto_semantic_when_explicit=False,
            resolution=None,
            clarification=None,
            explicit_error=None,
            runtime_bundle=None,
            context_mode=None,
        )
    model: SemanticModelRow | None = None
    pinned = (ask_settings.default_semantic_model_id or "").strip()
    if pinned:
        try:
            candidate = session.get(SemanticModelRow, uuid.UUID(pinned))
        except ValueError:
            candidate = None
        if (
            candidate is not None
            and candidate.workspace_id == workspace_id
            and candidate.project_id == project_id
            and candidate.active_version_id
        ):
            model = candidate
    if model is None:
        published = _published_models_for_project(session, workspace_id=workspace_id, project_id=project_id)
        if len(published) == 1:
            model = published[0]
    if model is None:
        return StructuredAskPrecedence(
            force_ossie=False,
            skip_auto_semantic_when_explicit=False,
            resolution=None,
            clarification=None,
            explicit_error=None,
            runtime_bundle=None,
            context_mode=None,
        )
    return _resolve_explicit_model(
        session,
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id,
        source=ChatContextSource(type="semantic_model", id=str(model.id), name=model.name),
        semantic_context=SemanticContextService(),
        question=question,
        session_analysis_context=session_analysis_context,
        auto_attached=True,
    )


def _resolve_automatic_table(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    question: str,
) -> StructuredAskPrecedence:
    tokens = _question_tokens(question)
    if len(tokens) < 1:
        return StructuredAskPrecedence(
            force_ossie=False,
            skip_auto_semantic_when_explicit=False,
            resolution=None,
            clarification=None,
            explicit_error=None,
            runtime_bundle=None,
            context_mode=None,
        )
    registry = ConnectorRegistryService(session, settings=settings)
    discovery = MetadataDiscoveryService(registry, settings=settings)
    candidates: list[tuple[float, RawTableRef, str]] = []
    for connector in registry.list_connectors(workspace_id=workspace_id, project_id=project_id, enabled=True):
        try:
            payload = discovery.list_tables(
                connector.id,
                workspace_id=workspace_id,
                project_id=project_id,
                limit=200,
            )
        except Exception:
            continue
        for row in payload.get("tables") or []:
            name = str(row.get("name") or "")
            schema = row.get("schema")
            label = ".".join(p for p in (schema, name) if p)
            score = _match_score(tokens, label, name)
            if score < 0.55:
                continue
            ref = RawTableRef(
                connector_id=connector.id,
                catalog=row.get("catalog"),
                schema=schema,
                table=name,
            )
            candidates.append((score, ref, label or name))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return StructuredAskPrecedence(
            force_ossie=False,
            skip_auto_semantic_when_explicit=False,
            resolution=None,
            clarification=None,
            explicit_error=None,
            runtime_bundle=None,
            context_mode=None,
        )
    top_score = candidates[0][0]
    strong = [c for c in candidates if c[0] >= max(0.75, top_score - 0.05)]
    if len(strong) == 1 and strong[0][0] >= 0.75:
        _, ref, label = strong[0]
        built = _raw_table_resolution(
            session,
            settings=settings,
            workspace_id=workspace_id,
            project_id=project_id,
            ref=ref,
            question=question,
            display_name=label,
        )
        if isinstance(built, str):
            return StructuredAskPrecedence(
                force_ossie=False,
                skip_auto_semantic_when_explicit=False,
                resolution=None,
                clarification=None,
                explicit_error=None,
                runtime_bundle=None,
                context_mode=None,
            )
        built["explicit_structured"] = False
        built["matched_alias"] = "auto_single_table"
        return StructuredAskPrecedence(
            force_ossie=True,
            skip_auto_semantic_when_explicit=False,
            resolution=built,
            clarification=None,
            explicit_error=None,
            runtime_bundle=None,
            context_mode="RAW_TABLE",
        )
    if len(strong) >= 2:
        options: list[dict[str, str]] = []
        seen: set[str] = set()
        for _, ref, label in strong[:8]:
            stable = encode_raw_table_id(
                connector_id=ref.connector_id,
                catalog=ref.catalog,
                schema=ref.schema,
                table=ref.table,
            )
            if stable in seen:
                continue
            seen.add(stable)
            options.append({"type": "table", "id": stable, "name": label})
        if options:
            return StructuredAskPrecedence(
                force_ossie=True,
                skip_auto_semantic_when_explicit=False,
                resolution=None,
                clarification=ClarificationPayload(
                    reason="AMBIGUOUS_DATA_SOURCE",
                    message="I found multiple possible data sources. Which one should I use?",
                    options=options,
                ),
                explicit_error=None,
                runtime_bundle=None,
                context_mode=None,
            )
    return StructuredAskPrecedence(
        force_ossie=False,
        skip_auto_semantic_when_explicit=False,
        resolution=None,
        clarification=None,
        explicit_error=None,
        runtime_bundle=None,
        context_mode=None,
    )


def _resolve_registry_metric_key(ctx: SemanticContextService, metric: SemanticMetricRow) -> str | None:
    registry = ctx.registry
    candidates: list[str] = [metric.key, metric.name, *(metric.synonyms or [])]
    for raw in candidates:
        name = (raw or "").strip()
        if not name:
            continue
        if name in registry.metrics:
            return name
    lowered = {str(k).casefold(): k for k in registry.metrics}
    for raw in candidates:
        name = (raw or "").strip().casefold()
        if name in lowered:
            return str(lowered[name])
    return None


def _question_tokens(question: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", question.casefold()))


def _match_score(tokens: set[str], label: str, table_name: str) -> float:
    hay = f"{label} {table_name}".casefold()
    name_cf = table_name.casefold()
    if name_cf and name_cf in hay:
        pass
    if name_cf and any(name_cf in token or token in name_cf for token in tokens if len(token) >= 4):
        return 0.9
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in hay or t in table_name.casefold())
    if hits == 0:
        return 0.0
    compact = table_name.casefold().replace("_", "")
    for t in tokens:
        if len(t) >= 4 and t in compact:
            hits += 1
    return min(1.0, hits / max(len(tokens), 1) + (0.25 if table_name.casefold() in " ".join(tokens) else 0))
