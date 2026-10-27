"""Config-driven enrichment, breakdown NL, and governed join compile for semantic runtime."""
from __future__ import annotations

import json
import re
from typing import Any

_DEFAULT_BREAKDOWN_CUES = (
    "bandingkan",
    "compare",
    "comparison",
    "breakdown",
    "dibanding",
    "perbandingan",
    " per ",
    " by ",
    "group by",
    "grouped by",
)


def merge_glossary_into_runtime_extensions(governance: dict[str, Any]) -> dict[str, Any] | None:
    """Fold published glossary phrase mappings into runtime extensions at load time."""
    if not isinstance(governance, dict):
        return None
    base = governance.get("runtime_extensions")
    glossary = governance.get("glossary")
    if not glossary and not base:
        return None
    merged: dict[str, Any] = dict(base) if isinstance(base, dict) else {}
    if isinstance(glossary, list) and glossary:
        phrase_map: list[dict[str, Any]] = []
        for entry in glossary:
            if not isinstance(entry, dict):
                continue
            dims = entry.get("related_dimension_keys") or []
            if not dims:
                continue
            phrases = [str(entry.get("term") or "").strip()]
            phrases.extend(str(s) for s in (entry.get("synonyms") or []) if s)
            phrases = [p for p in dict.fromkeys(phrases) if p]
            if phrases:
                phrase_map.append({"phrases": phrases, "dimension": str(dims[0])})
        if phrase_map:
            breakdown = dict(merged.get("breakdown") or {})
            existing = breakdown.get("phrase_map") or []
            combined = [*existing, *phrase_map]
            deduped: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
            for item in combined:
                if not isinstance(item, dict):
                    continue
                dim = str(item.get("dimension") or "")
                phr = tuple(str(p) for p in (item.get("phrases") or []) if p)
                if dim and phr:
                    deduped[(dim, phr)] = {"phrases": list(phr), "dimension": dim}
            breakdown["phrase_map"] = list(deduped.values())
            merged["breakdown"] = breakdown
    return merged or None


def question_requests_breakdown(question: str, extensions: dict[str, Any] | None = None) -> bool:
    q = question.casefold()
    cues = _DEFAULT_BREAKDOWN_CUES
    if extensions:
        custom = (extensions.get("breakdown") or {}).get("cues")
        if isinstance(custom, list) and custom:
            cues = tuple(str(c).casefold() for c in custom)
    if any(cue in q for cue in cues):
        return True
    if re.search(r"\btop\s+\d+\b", q):
        return True
    if "berdasarkan" in q:
        return True
    return bool(re.search(r"\bper\b", q))


def infer_breakdown_dimensions(
    question: str,
    allowed: set[str],
    extensions: dict[str, Any] | None,
) -> list[str]:
    if not allowed or not extensions or not question_requests_breakdown(question, extensions):
        return []
    q = question.casefold()
    phrase_map = (extensions.get("breakdown") or {}).get("phrase_map") or []
    for entry in phrase_map:
        if not isinstance(entry, dict):
            continue
        dim_key = str(entry.get("dimension") or "").strip()
        if not dim_key or dim_key not in allowed:
            continue
        phrases = entry.get("phrases") or []
        if any(str(phrase).casefold() in q for phrase in phrases):
            return [dim_key]
    return []


def _infer_dimension_filter(question: str, join_spec: dict[str, Any]) -> str | None:
    filt = join_spec.get("dimension_filter")
    if not isinstance(filt, dict):
        return None
    token_values = filt.get("token_values") or {}
    if not isinstance(token_values, dict):
        return None
    q = question.casefold()
    for token, label in token_values.items():
        token_s = str(token).casefold()
        label_s = str(label)
        if re.search(rf"\b{re.escape(token_s)}\b", q):
            return label_s
        if label_s.casefold() in q:
            return label_s
    return None


def _question_matches_join_context(question: str, join_spec: dict[str, Any]) -> bool:
    when = join_spec.get("when") or {}
    dim_terms = [str(t).casefold() for t in (when.get("dimension_terms") or [])]
    ctx_terms = [str(t).casefold() for t in (when.get("context_terms") or [])]
    exclude_terms = [str(t).casefold() for t in (when.get("exclude_dimension_terms") or [])]
    q = question.casefold()
    if exclude_terms and any(t in q for t in exclude_terms):
        return False
    if dim_terms and not any(t in q for t in dim_terms):
        return False
    if ctx_terms and not any(t in q for t in ctx_terms):
        return False
    return True


def qualify_metric_expression(expression: str, *, left_dataset: str, left_alias: str) -> str:
    expr = expression.replace(f"{left_dataset}.", f"{left_alias}.")

    def repl(match: re.Match[str]) -> str:
        func = match.group(1)
        inner = match.group(2).strip()
        if inner.upper().startswith("DISTINCT"):
            rest = inner[8:].strip()
            if not rest.startswith(f"{left_alias}."):
                rest = f"{left_alias}.{rest}"
            return f"{func}(DISTINCT {rest})"
        if inner.startswith(f"{left_alias}."):
            return match.group(0)
        return f"{func}({left_alias}.{inner})"

    return re.sub(
        r"\b(COUNT|SUM|AVG|MIN|MAX)\(\s*([^)]+)\s*\)",
        repl,
        expr,
        flags=re.IGNORECASE,
    )


def try_compile_governed_join_sql(
    *,
    extensions: dict[str, Any] | None,
    datasets: dict[str, dict[str, Any]],
    metric_base_dataset: str,
    metric_expression: str,
    question: str,
    row_filter: str | None,
    period_predicate: str | None,
    extra_predicates: list[str] | None,
    sql_max_rows: int,
) -> str | None:
    if not extensions:
        return None
    joins = extensions.get("governed_joins") or []
    for join_spec in joins:
        if not isinstance(join_spec, dict):
            continue
        when = join_spec.get("when") or {}
        if str(when.get("metric_base_dataset") or "") != metric_base_dataset:
            continue
        if not _question_matches_join_context(question, join_spec):
            continue

        left = join_spec.get("left") or {}
        right = join_spec.get("right") or {}
        on = join_spec.get("join_keys") or join_spec.get("on") or {}
        left_ds = str(left.get("dataset") or "")
        right_ds = str(right.get("dataset") or "")
        left_alias = str(left.get("alias") or "d")
        right_alias = str(right.get("alias") or "c")
        left_source = str((datasets.get(left_ds) or {}).get("source") or "").strip()
        right_source = str((datasets.get(right_ds) or {}).get("source") or "").strip()
        if not left_source or not right_source:
            continue

        dim_filter = _infer_dimension_filter(question, join_spec)
        breakdown = join_spec.get("breakdown") or {}
        has_breakdown = bool(breakdown.get("select_expression"))
        wants_breakdown = has_breakdown and _question_matches_join_context(question, join_spec) and not (
            dim_filter and "top" not in question.casefold()
        )
        if not wants_breakdown and not dim_filter:
            continue

        metric_expr = qualify_metric_expression(
            metric_expression,
            left_dataset=left_ds,
            left_alias=left_alias,
        )
        predicates: list[str] = []
        if row_filter:
            predicates.append(f"({row_filter.replace(f'{left_ds}.', f'{left_alias}.')})")
        if period_predicate:
            predicates.append(period_predicate.replace(f"{left_ds}.", f"{left_alias}."))
        if extra_predicates:
            predicates.extend(extra_predicates)
        filt = join_spec.get("dimension_filter") or {}
        filter_col = str(filt.get("column") or "")
        if dim_filter and filter_col:
            predicates.append(f"{filter_col} = '{dim_filter}'")

        top_match = re.search(r"\btop\s+(\d+)\b", question, flags=re.IGNORECASE)
        limit = int(top_match.group(1)) if top_match else sql_max_rows

        join_type = str(right.get("join_type") or "inner").upper()
        left_key = str(on.get("left_key") or "")
        right_key = str(on.get("right_key") or "")

        if wants_breakdown:
            select_expr = str(breakdown.get("select_expression") or "")
            result_alias = str(breakdown.get("result_alias") or "breakdown_value")
            group_expr = str(breakdown.get("group_by_expression") or select_expr)
            projections = [f"{select_expr} AS {result_alias}", f"{metric_expr} AS metric_value"]
            sql = [
                "SELECT",
                "  " + ",\n  ".join(projections),
                f"FROM {left_source} {left_alias}",
                f"{join_type} JOIN {right_source} {right_alias} ON {left_alias}.{left_key} = {right_alias}.{right_key}",
            ]
            if predicates:
                sql.append("WHERE " + "\n  AND ".join(predicates))
            sql.append(f"GROUP BY {group_expr}")
            sql.append("ORDER BY metric_value DESC")
            sql.append(f"LIMIT {limit}")
            return "\n".join(sql)

        projections = [f"{metric_expr} AS metric_value"]
        sql = [
            "SELECT",
            "  " + ",\n  ".join(projections),
            f"FROM {left_source} {left_alias}",
            f"{join_type} JOIN {right_source} {right_alias} ON {left_alias}.{left_key} = {right_alias}.{right_key}",
        ]
        if predicates:
            sql.append("WHERE " + "\n  AND ".join(predicates))
        sql.append(f"LIMIT {limit}")
        return "\n".join(sql)
    return None


def governed_join_state_patch(
    *,
    extensions: dict[str, Any] | None,
    datasets: dict[str, dict[str, Any]],
    sql: str,
    datasource_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not extensions or "join" not in sql.casefold():
        return None
    joins = extensions.get("governed_joins") or []
    for join_spec in joins:
        if not isinstance(join_spec, dict):
            continue
        validation = join_spec.get("validation_tables") or {}
        if not isinstance(validation, dict):
            continue
        table_entries: list[dict[str, Any]] = []
        sources: list[str] = []
        for ds_name, columns in validation.items():
            source = str((datasets.get(str(ds_name)) or {}).get("source") or "").strip()
            if not source or source.casefold() not in sql.casefold():
                break
            sources.append(source)
            table_entries.append(
                {
                    "qualified_name": source,
                    "columns": [str(c) for c in (columns or [])],
                }
            )
        else:
            if len(table_entries) < 2:
                continue
            from app.ask_data.physical_identifiers import normalize_table_key

            allowed = sorted({normalize_table_key(s) for s in sources})
            primary = table_entries[0]["qualified_name"]
            merged_ds = dict(datasource_context or {})
            merged_ds["allowed_physical_tables"] = allowed
            merged_ds.setdefault("legacy_fallback", False)
            return {
                "raw_table_policy": {
                    "qualified_name": primary,
                    "columns": table_entries[0]["columns"],
                    "tables": table_entries,
                },
                "datasource_context": merged_ds,
            }
    return None


def apply_runtime_extensions(
    extensions: dict[str, Any],
    *,
    datasets: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    dataset_fields: dict[str, dict[str, dict[str, Any]]],
) -> None:
    field_block = extensions.get("field_enrichment") or {}
    for item in field_block.get("time_dimensions") or []:
        if not isinstance(item, dict):
            continue
        ds_name = str(item.get("dataset") or "")
        field_name = str(item.get("field") or "")
        fields = dataset_fields.get(ds_name) or {}
        field = fields.get(field_name)
        if not field:
            continue
        dim_meta = field.setdefault("dimension", {})
        if isinstance(dim_meta, dict):
            dim_meta["is_time"] = True

    col_exprs = field_block.get("column_expressions") or {}
    if isinstance(col_exprs, dict):
        for fname, col in col_exprs.items():
            for fields in dataset_fields.values():
                field = fields.get(str(fname))
                if not field:
                    continue
                expr = field.get("expression")
                if isinstance(expr, dict) and expr.get("dialects"):
                    continue
                field["expression"] = {
                    "dialects": [{"dialect": "ANSI_SQL", "expression": str(col)}],
                }
                field.setdefault("dimension", {})

    metric_enrichment = extensions.get("metric_enrichment") or {}
    if isinstance(metric_enrichment, dict):
        for metric_key, spec in metric_enrichment.items():
            if not isinstance(spec, dict):
                continue
            metric = metrics.get(metric_key)
            if not metric:
                continue
            metric["description"] = spec.get("description") or metric.get("description")
            ai = metric.setdefault("ai_context", {})
            if not isinstance(ai, dict):
                ai = {}
                metric["ai_context"] = ai
            existing = ai.get("synonyms") if isinstance(ai.get("synonyms"), list) else []
            merged = list(dict.fromkeys([*(spec.get("synonyms") or []), *existing]))
            ai["synonyms"] = merged
            if spec.get("display_name"):
                ai["display_name"] = spec["display_name"]
            expr = spec.get("expression")
            if expr:
                dialects = metric.get("expression", {}).get("dialects")
                if isinstance(dialects, list) and dialects:
                    dialects[0]["expression"] = str(expr)

    synthetic = extensions.get("synthetic_metrics") or {}
    enrich_all = metric_enrichment if isinstance(metric_enrichment, dict) else {}
    if isinstance(synthetic, dict):
        for metric_key, spec in synthetic.items():
            if metric_key in metrics or not isinstance(spec, dict):
                continue
            enrich = enrich_all.get(metric_key, {})
            if not isinstance(enrich, dict):
                enrich = {}
            expr = str(enrich.get("expression") or "COUNT(1)")
            metrics[metric_key] = {
                "name": metric_key,
                "description": spec.get("description") or enrich.get("description") or metric_key,
                "expression": {
                    "dialects": [{"dialect": "ANSI_SQL", "expression": expr}],
                },
                "custom_extensions": [
                    {
                        "vendor_name": "TEMPO",
                        "data": json.dumps(
                            {
                                "base_dataset": spec["base_dataset"],
                                "metric_id": spec["metric_id"],
                                "allowed_dimensions": spec.get("allowed_dimensions") or [],
                            }
                        ),
                    }
                ],
                "ai_context": {
                    "display_name": enrich.get("display_name") or metric_key.replace("_", " ").title(),
                    "synonyms": list(enrich.get("synonyms") or []),
                },
            }


def display_name_for_metric(metric_key: str, extensions: dict[str, Any] | None) -> str | None:
    if not extensions:
        return None
    spec = (extensions.get("metric_enrichment") or {}).get(metric_key)
    if not isinstance(spec, dict):
        return None
    return str(spec.get("display_name") or spec.get("description") or "").strip() or None


def metric_resolver_score_bonus(
    normalized_question: str,
    metric_name: str,
    extensions: dict[str, Any] | None,
) -> int:
    if not extensions:
        return 0
    rules = extensions.get("metric_resolver_rules") or []
    name_cf = metric_name.casefold()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        when_any = [str(t).casefold() for t in (rule.get("when_any") or [])]
        when_all = [str(t).casefold() for t in (rule.get("when_all") or [])]
        if when_any and not any(t in normalized_question for t in when_any):
            continue
        if when_all and not all(t in normalized_question for t in when_all):
            continue
        prefer = str(rule.get("prefer_metric_contains") or "").casefold()
        if prefer and prefer not in name_cf:
            continue
        return int(rule.get("score_bonus") or 0)
    return 0


def coerce_suggested_metric_metadata(
    *,
    key: str,
    expression: str,
    name: str | None,
    extensions: dict[str, Any] | None,
) -> tuple[str, str, str]:
    expr = (expression or "").strip()
    spec = (extensions or {}).get("metric_enrichment", {}).get(key) if extensions else None
    if isinstance(spec, dict) and spec.get("expression"):
        expr = str(spec["expression"])
    elif re.match(r"^SUM\s*\(\s*customer_id\s*\)$", expr, re.I):
        expr = "COUNT(DISTINCT customer_id)"
    elif re.match(r"^SUM\s*\(\s*transaction_id\s*\)$", expr, re.I):
        expr = "COUNT(transaction_id)"

    display = (name or "").strip()
    if display.lower().startswith("suggested metric "):
        display = display[17:].strip()
    if isinstance(spec, dict) and spec.get("display_name"):
        display = str(spec["display_name"])
    elif not display or display == key:
        display = display_name_for_metric(key, extensions) or key.replace("_", " ").title()

    definition = spec.get("description") if isinstance(spec, dict) else None
    if not definition:
        definition = f"Governed metric {display}."
    return display, expr, str(definition)
