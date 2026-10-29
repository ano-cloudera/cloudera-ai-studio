from __future__ import annotations

from dataclasses import dataclass
import re

import sqlglot
from sqlglot import exp

from app.semantic.context import SemanticContextService


@dataclass(frozen=True)
class ValidatedSQL:
    valid: bool
    sql: str | None = None
    error: str | None = None


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|invalidate|refresh)\b",
    re.IGNORECASE,
)

_ALLOWED_FUNCTIONS = {
    "abs", "and", "avg", "case", "cast", "ceil", "ceiling", "coalesce", "concat", "count",
    "date_add", "date_format", "date_sub", "datediff", "floor", "greatest", "if",
    "least", "lower", "ltrim", "max", "min", "month", "nullif", "or", "round", "rtrim",
    "substr", "substring", "sum", "trim", "upper", "year", "date_trunc", "timestamp_trunc",
}


def has_projected_star(root: exp.Expression) -> bool:
    """True for `SELECT *` / `t.*`; `COUNT(*)` is an aggregate and stays allowed."""
    return any(
        star.find_ancestor(exp.Count) is None
        for select in root.find_all(exp.Select)
        for star in select.find_all(exp.Star)
    )


def _table_name(table: exp.Table) -> str:
    return ".".join(value for value in (table.catalog, table.db, table.name) if value).casefold()


def validate_sql(sql: str, context: SemanticContextService, *, max_rows: int = 200) -> ValidatedSQL:
    if not sql or not sql.strip():
        return ValidatedSQL(False, error="Empty SQL")
    if _FORBIDDEN.search(sql):
        return ValidatedSQL(False, error="DDL/DML statements are not allowed")
    try:
        statements = sqlglot.parse(sql, read="hive")
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

    ctes = {cte.alias_or_name.casefold() for cte in root.find_all(exp.CTE)}
    aliases: dict[str, tuple[str, frozenset[str]]] = {}
    physical_tables = 0
    for table in root.find_all(exp.Table):
        name = _table_name(table)
        if not table.db and not table.catalog and name in ctes:
            continue
        try:
            policy = context.table_policy(name)
        except ValueError as exc:
            return ValidatedSQL(False, error=str(exc))
        physical_tables += 1
        aliases[table.alias_or_name.casefold()] = (name, policy.columns)
        aliases[name] = (name, policy.columns)
    if physical_tables == 0:
        return ValidatedSQL(False, error="An approved table is required")
    if physical_tables > 1:
        return ValidatedSQL(False, error="Runtime joins are not allowed; use a published cross-domain view")

    select_aliases = {alias.alias.casefold() for alias in root.find_all(exp.Alias) if alias.alias}
    for column in root.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            return ValidatedSQL(False, error="SELECT * is not allowed")
        name = column.name.casefold()
        qualifier = (column.table or "").casefold()
        if qualifier:
            target = aliases.get(qualifier)
            if target is None:
                return ValidatedSQL(False, error=f"Unknown table alias: {qualifier}")
            if name not in target[1]:
                return ValidatedSQL(False, error=f"Column not allowed for {target[0]}: {name}")
        elif name not in select_aliases and not any(name in columns for _, columns in aliases.values()):
            return ValidatedSQL(False, error=f"Column not allowed: {name}")

    limit = root.args.get("limit")
    if limit is None:
        root = root.limit(max_rows)
    else:
        expression = limit.expression
        if not isinstance(expression, exp.Literal) or not expression.is_int or int(expression.this) <= 0:
            return ValidatedSQL(False, error="LIMIT must be a positive integer")
        if int(expression.this) > max_rows:
            root.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    return ValidatedSQL(True, sql=root.sql(dialect="hive"))
