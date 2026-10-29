from __future__ import annotations

from typing import Any

from app.ask_data.physical_identifiers import normalize_table_key
from app.ask_data.types import DatasourceExecutionContext
from app.semantic.context import SemanticContextService, TablePolicy
from app.sql.validator import ValidatedSQL, _FORBIDDEN, _ALLOWED_FUNCTIONS, _table_name, has_projected_star
import sqlglot
from sqlglot import exp


def validate_ask_data_sql(
    sql: str,
    context: SemanticContextService,
    *,
    state: dict[str, Any] | None = None,
    max_rows: int = 200,
) -> ValidatedSQL:
    raw_ctx = (state or {}).get("datasource_context")
    ds_ctx = DatasourceExecutionContext.from_dict(raw_ctx) if isinstance(raw_ctx, dict) else None
    read_dialect = ds_ctx.dialect if ds_ctx and not ds_ctx.legacy_fallback else "hive"
    if read_dialect == "duckdb":
        read_dialect = "duckdb"

    if not sql or not sql.strip():
        return ValidatedSQL(False, error="Empty SQL")
    if _FORBIDDEN.search(sql):
        return ValidatedSQL(False, error="DDL/DML statements are not allowed")
    try:
        statements = sqlglot.parse(sql, read=read_dialect)
    except Exception as exc:
        return ValidatedSQL(False, error=f"SQL parse error: {exc}")
    if len(statements) != 1:
        return ValidatedSQL(False, error="Only one SQL statement is allowed")
    root = statements[0]
    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return ValidatedSQL(False, error=f"Only SELECT queries are allowed, got {type(root).__name__}")
    if has_projected_star(root):
        return ValidatedSQL(False, error="SELECT * is not allowed")

    for function in root.find_all(exp.Func):
        name = function.name if isinstance(function, exp.Anonymous) else function.sql_name()
        normalized = str(name).casefold()
        if normalized not in _ALLOWED_FUNCTIONS:
            return ValidatedSQL(False, error=f"Function not allowed: {normalized}")

    raw_policy = (state or {}).get("raw_table_policy") if isinstance(state, dict) else None
    table_policies: dict[str, frozenset[str]] = {}
    if isinstance(raw_policy, dict) and raw_policy.get("tables"):
        for entry in raw_policy.get("tables") or []:
            if not isinstance(entry, dict):
                continue
            qn = str(entry.get("qualified_name") or "")
            if not qn:
                continue
            table_policies[normalize_table_key(qn)] = frozenset(
                str(c).casefold() for c in (entry.get("columns") or []) if c
            )
    ossie_source = _ossie_source_for_state(context, state)
    ctes = {cte.alias_or_name.casefold() for cte in root.find_all(exp.CTE)}
    aliases: dict[str, tuple[str, frozenset[str]]] = {}
    physical_tables = 0
    allowed_physical = (
        ds_ctx.allowed_physical_tables
        if ds_ctx and not ds_ctx.legacy_fallback
        else frozenset()
    )
    for table in root.find_all(exp.Table):
        name = _table_name(table)
        if not table.db and not table.catalog and name.casefold() in ctes:
            continue
        if allowed_physical:
            key = normalize_table_key(name)
            if key not in allowed_physical:
                return ValidatedSQL(False, error=f"Table not allowed: {name}")
            if table_policies and key in table_policies:
                columns = table_policies[key]
            elif isinstance(raw_policy, dict) and raw_policy.get("columns") is not None:
                columns = frozenset(str(c).casefold() for c in raw_policy.get("columns") or [])
            else:
                policy = context.table_policy(ossie_source) if ossie_source else None
                if policy is None:
                    return ValidatedSQL(False, error="Semantic table policy unavailable")
                columns = policy.columns
        else:
            try:
                policy = context.table_policy(name)
            except ValueError as exc:
                return ValidatedSQL(False, error=str(exc))
            columns = policy.columns
        physical_tables += 1
        aliases[table.alias_or_name.casefold()] = (name, columns)
        aliases[name.casefold()] = (name, columns)
    if physical_tables == 0:
        return ValidatedSQL(False, error="An approved table is required")
    if physical_tables > 1 and not (allowed_physical and physical_tables <= len(allowed_physical)):
        return ValidatedSQL(False, error="Runtime joins are not allowed; use a published cross-domain view")

    select_aliases = {alias.alias.casefold() for alias in root.find_all(exp.Alias) if alias.alias}
    for column in root.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            return ValidatedSQL(False, error="SELECT * is not allowed")
        col_name = column.name.casefold()
        qualifier = (column.table or "").casefold()
        if qualifier:
            target = aliases.get(qualifier)
            if target is None:
                return ValidatedSQL(False, error=f"Unknown table alias: {qualifier}")
            if col_name not in target[1]:
                return ValidatedSQL(False, error=f"Column not allowed for {target[0]}: {col_name}")
        elif col_name not in select_aliases and not any(col_name in columns for _, columns in aliases.values()):
            return ValidatedSQL(False, error=f"Column not allowed: {col_name}")

    limit = root.args.get("limit")
    if limit is None:
        root = root.limit(max_rows)
    else:
        expression = limit.expression
        if not isinstance(expression, exp.Literal) or not expression.is_int or int(expression.this) <= 0:
            return ValidatedSQL(False, error="LIMIT must be a positive integer")
        if int(expression.this) > max_rows:
            root.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    out_dialect = read_dialect if read_dialect != "duckdb" else "duckdb"
    return ValidatedSQL(True, sql=root.sql(dialect=out_dialect))


def _ossie_source_for_state(context: SemanticContextService, state: dict[str, Any] | None) -> str | None:
    if not state:
        return None
    resolution = state.get("semantic_resolution")
    if not isinstance(resolution, dict) or resolution.get("status") != "resolved":
        return None
    metric = resolution.get("metric")
    if not metric:
        return None
    try:
        definition = resolution.get("definition") or context.metric_definition(str(metric))
        dataset_name = definition.get("base_dataset")
        if not dataset_name:
            return None
        return str(context.datasets[dataset_name]["source"])
    except Exception:
        return None
