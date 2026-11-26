"""A semantic model drafted from the data: each table is profiled, the model assigned to Ask Data writes the entity, its dimensions and
metrics, and a second call proposes joins and business terms. The model proposes; the data decides what is offered:

- every column a draft names must exist in the table,
- every metric is run once on the data, and one that fails is dropped,
- a metric that filters on a value the column does not hold is dropped,
- a join is offered only when the values of one side are found on the other,
- a synonym given to two items is removed from both, and terms are not tied to metrics (a shared phrase made the resolver pick the
  wrong metric).

What is dropped is returned with the reason, so the reviewer sees what the checks did. Nothing is saved here: the result feeds the
review step, and only what the user accepts is created, in a draft version.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp

from app.connectors.sql_compose import SQL_DIALECT
from app.semantic_registry.table_profile import (
    SAMPLE_SIZE,
    JoinCheck,
    Runner,
    TableProfile,
    check_expressions,
    check_join,
)

logger = logging.getLogger(__name__)

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
LANGUAGES = {"en": "English", "id": "Bahasa Indonesia"}
JOIN_CONFIRMED = 0.9
WHOLE_TABLE_ROWS = 2_000_000  # up to this size a metric is checked on the whole table, so the value shown is the real one
MAX_HEADLINE = 4
MAX_DIMENSIONS = 25
MAX_METRICS = 15
MAX_TERMS = 8


# --- what the model writes -------------------------------------------------------------------------------------------------


class DraftDimension(BaseModel):
    column: str
    name: str
    description: str = ""
    kind: Literal["time", "category", "place", "identifier", "attribute"] = "attribute"
    synonyms: list[str] = Field(default_factory=list)


class DraftMetric(BaseModel):
    name: str
    expression: str
    unit: str = ""
    description: str = ""
    better: Literal["up", "down", "neutral"] = "neutral"
    synonyms: list[str] = Field(default_factory=list)


class TableDraft(BaseModel):
    name: str
    description: str = ""
    primary_key: str = ""
    dimensions: list[DraftDimension] = Field(default_factory=list)
    metrics: list[DraftMetric] = Field(default_factory=list)
    headline: list[str] = Field(default_factory=list)


class DraftRelationship(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    description: str = ""


class DraftTerm(BaseModel):
    term: str
    definition: str
    synonyms: list[str] = Field(default_factory=list)


class HeadlinePick(BaseModel):
    table: str
    metric: str


class LinksDraft(BaseModel):
    relationships: list[DraftRelationship] = Field(default_factory=list)
    headline: list[HeadlinePick] = Field(default_factory=list)
    terms: list[DraftTerm] = Field(default_factory=list)


# --- the input of one table --------------------------------------------------------------------------------------------------


@dataclass
class DraftTable:
    """One selected table with its profile, where it lives and how to query it."""

    key: str
    connection_id: str
    profile: TableProfile
    run: Runner


@dataclass
class DraftResult:
    entities: list[dict] = field(default_factory=list)
    dimensions: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    glossary_suggestions: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    provider: str = ""

    def to_dict(self) -> dict:
        return {
            "entities": self.entities,
            "metrics": self.metrics,
            "dimensions": self.dimensions,
            "relationships": self.relationships,
            "glossary_suggestions": self.glossary_suggestions,
            "dropped": self.dropped,
            "notes": self.notes,
            "provider": self.provider,
            "drafted": True,
        }


# --- keys --------------------------------------------------------------------------------------------------------------------


def slug(text: str, fallback: str = "item") -> str:
    base = re.sub(r"\([^)]*\)", " ", text or "")
    base = re.sub(r"[^a-z0-9]+", "_", base.strip().lower()).strip("_")
    if base and not base[0].isalpha():
        base = f"x_{base}"
    return base[:64] or fallback


def unique(key: str, taken: set[str]) -> str:
    candidate, n = key, 2
    while candidate in taken:
        candidate = f"{key[:60]}_{n}"
        n += 1
    taken.add(candidate)
    return candidate


# --- checks ------------------------------------------------------------------------------------------------------------------


def _strip_table_prefix(expression: str, names: set[str]) -> str:
    """`orders.amount` -> `amount`: the runtime reads bare column names, and models often qualify them anyway."""
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\.(?=[A-Za-z_\"`])", re.I) if names else None
    return pattern.sub("", expression) if pattern else expression


def expression_problem(expression: str, profile: TableProfile) -> str | None:
    """Why a metric expression cannot be offered, judged from its SQL and the profile; None when it may be run."""
    dialect = SQL_DIALECT.get(profile.connector_type, "trino")
    try:
        tree = sqlglot.parse_one(expression, read=dialect)
    except Exception:  # noqa: BLE001
        return "Its SQL could not be read."
    if tree is None:
        return "Its SQL is empty."
    if tree.find(exp.Select) or tree.find(exp.Subquery):
        return "It contains a query of its own; a metric is one expression."
    if tree.find(exp.Window):
        return "It uses a window function; a metric aggregates rows."
    if not tree.find(exp.AggFunc):
        return "It does not aggregate rows (no SUM, COUNT, AVG, MIN or MAX)."
    known = {c.name.lower() for c in profile.columns}
    for column in tree.find_all(exp.Column):
        if column.name.lower() not in known:
            return f"It names a column the table does not have: {column.name}."
    # A filter on a value the column does not hold always counts nothing; only judged when every value of the column is known.
    for node in tree.find_all(exp.EQ, exp.In):
        column = node.find(exp.Column)
        if column is None:
            continue
        profiled = profile.column(column.name)
        if profiled is None or not profiled.top_values or profiled.distinct is None or profiled.distinct > len(profiled.top_values):
            continue
        values = {str(v) for v, _ in profiled.top_values}
        literals = [lit.this for lit in node.find_all(exp.Literal) if lit.is_string]
        missing = [v for v in literals if v not in values]
        if missing:
            return f"It filters {column.name} on '{missing[0]}', which the column does not hold (it holds {', '.join(sorted(values))})."
    return None


def aggregation_of(expression: str) -> str | None:
    match = re.match(r"^\s*(SUM|COUNT|AVG|MIN|MAX)\s*\(", expression, re.I)
    if not match:
        return None
    # The whole expression must be that one call ("SUM(a) / SUM(b)" is a ratio, not a sum).
    depth = 0
    for index, char in enumerate(expression.strip()):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return match.group(1).lower() if index == len(expression.strip()) - 1 else None
    return None


def clean_synonyms(items: list[dict]) -> int:
    """Remove a synonym that two items share, or that is another item's name. Returns how many were removed."""
    owners: dict[str, set[int]] = {}
    names = {str(item.get("name") or "").strip().lower(): i for i, item in enumerate(items)}
    for i, item in enumerate(items):
        for synonym in item.get("synonyms") or []:
            owners.setdefault(synonym.strip().lower(), set()).add(i)
    removed = 0
    for i, item in enumerate(items):
        kept = []
        seen: set[str] = set()
        for synonym in item.get("synonyms") or []:
            text = synonym.strip()
            low = text.lower()
            clash = len(owners.get(low, set())) > 1 or (low in names and names[low] != i)
            if not text or low in seen or clash or low == str(item.get("name") or "").strip().lower():
                removed += clash
                continue
            seen.add(low)
            kept.append(text)
        item["synonyms"] = kept[:6]
    return removed


# --- the model calls ---------------------------------------------------------------------------------------------------------


def _messages(prompt_file: str, payload: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": (PROMPTS / prompt_file).read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]


async def draft_table(provider: Any, table: DraftTable, *, language: str, context: str) -> TableDraft:
    payload = {"language": LANGUAGES.get(language, "English"), "table_profile": table.profile.for_prompt()}
    if context.strip():
        payload["business_context"] = context.strip()
    return await provider.generate_structured(_messages("semantic_draft.md", payload), TableDraft, temperature=0.1, max_tokens=6000)


async def draft_links(
    provider: Any,
    tables: list[tuple[DraftTable, TableDraft]],
    *,
    language: str,
    context: str,
    metrics: dict[str, list[str]] | None = None,
) -> LinksDraft:
    summary = []
    for table, draft in tables:
        summary.append(
            {
                "table": table.profile.table,
                "object": draft.name,
                "description": draft.description,
                "key": draft.primary_key or None,
                "metrics": (metrics or {}).get(table.key, []),
                "columns": [
                    {
                        "name": c.name,
                        "type": c.native_type,
                        "distinct": c.distinct,
                        **({"common_values": [v for v, _ in c.top_values[:5]]} if c.top_values else {}),
                    }
                    for c in table.profile.columns
                ],
            }
        )
    payload: dict[str, Any] = {"language": LANGUAGES.get(language, "English"), "tables": summary}
    if context.strip():
        payload["business_context"] = context.strip()
    return await provider.generate_structured(_messages("semantic_draft_links.md", payload), LinksDraft, temperature=0.1, max_tokens=3000)


# --- from drafts to suggestions ----------------------------------------------------------------------------------------------


def _dimension_type(normalized: str) -> str:
    return {"DATE": "date", "TIMESTAMP": "timestamp", "BOOLEAN": "boolean"}.get(normalized, "number" if normalized in {"INTEGER", "BIGINT", "DECIMAL", "FLOAT"} else "string")


def table_suggestions(table: DraftTable, draft: TableDraft, result: DraftResult, taken: dict[str, set[str]]) -> None:
    """The entity, dimensions and metrics of one table, after the checks that need no query (columns, SQL shape, values)."""
    profile = table.profile
    entity_key = table.key
    pk = draft.primary_key.strip()
    if pk and profile.column(pk) is None:
        pk = ""
    if not pk and profile.primary_key:
        pk = ",".join(profile.primary_key)
    result.entities.append(
        {
            "suggestion_id": f"entity:{entity_key}",
            "key": entity_key,
            "name": draft.name.strip() or profile.table,
            "description": draft.description.strip(),
            "connection_id": table.connection_id,
            "catalog": profile.catalog,
            "schema": profile.schema,
            "table_name": profile.table,
            "primary_key": pk or None,
            "source_type": profile.connector_type,
            "metadata": {
                "column_count": len(profile.columns) + len(profile.skipped_columns),
                "physical_columns": [{"name": c.name, "normalized_type": c.normalized_type} for c in profile.columns],
                "drafted_from_rows": profile.sample_rows,
            },
            "evidence": {"row_count": profile.row_count, "profiled_rows": profile.sample_rows},
            "status": "suggested",
        }
    )

    used_columns: set[str] = set()
    for dim in draft.dimensions[:MAX_DIMENSIONS]:
        column = profile.column(dim.column)
        if column is None:
            result.dropped.append({"type": "dimension", "name": dim.name, "table": profile.table, "reason": f"The table has no column {dim.column}."})
            continue
        if column.name.lower() in used_columns:
            continue
        used_columns.add(column.name.lower())
        key = unique(slug(column.name, "dimension"), taken["dimension"])
        if key != slug(column.name, "dimension"):
            taken["dimension"].discard(key)
            key = unique(f"{entity_key}_{slug(column.name, 'dimension')}"[:64], taken["dimension"])
        examples = [v for v, _ in column.top_values[:5]]
        result.dimensions.append(
            {
                "suggestion_id": f"dimension:{key}",
                "key": key,
                "name": dim.name.strip() or column.name,
                "description": dim.description.strip(),
                "source_entity_key": entity_key,
                "source_column": column.name,
                "data_type": _dimension_type(column.normalized_type),
                "category": {"time": "TIME", "place": "GEO", "identifier": "IDENTIFIER"}.get(dim.kind, "ATTRIBUTE"),
                "synonyms": [s for s in dim.synonyms if isinstance(s, str)],
                "evidence": {"distinct": column.distinct, "examples": examples},
                "status": "suggested",
            }
        )

    table_names = {profile.table, entity_key}
    headline = [h.strip().lower() for h in draft.headline]
    for metric in draft.metrics[:MAX_METRICS]:
        expression = _strip_table_prefix(metric.expression.strip().rstrip(";"), table_names)
        problem = expression_problem(expression, profile)
        if problem:
            result.dropped.append({"type": "metric", "name": metric.name, "table": profile.table, "expression": expression, "reason": problem})
            continue
        key = unique(slug(metric.name, "metric"), taken["metric"])
        rank = headline.index(metric.name.strip().lower()) + 1 if metric.name.strip().lower() in headline else None
        extension: dict[str, Any] = {}
        if rank and rank <= 4:
            extension["headline"] = rank
        if metric.better in ("up", "down"):
            extension["better"] = metric.better
        result.metrics.append(
            {
                "suggestion_id": f"metric:{key}",
                "key": key,
                "name": metric.name.strip(),
                "expression": expression,
                "aggregation": aggregation_of(expression),
                "unit": metric.unit.strip() or None,
                "description": metric.description.strip(),
                "business_definition": metric.description.strip(),
                "source_entity_key": entity_key,
                "synonyms": [s for s in metric.synonyms if isinstance(s, str)],
                "better": metric.better,
                "metadata": {"reference_extension": extension} if extension else {},
                "status": "suggested",
            }
        )


def run_metric_checks(table: DraftTable, result: DraftResult) -> None:
    """Run this table's metrics on the data; keep the ones that run, with the value they gave. A table of reasonable size is read
    whole, so the value shown is the real one; a larger one is read on the profiled sample."""
    mine = [m for m in result.metrics if m["source_entity_key"] == table.key]
    rows = table.profile.row_count
    whole = rows is not None and rows <= WHOLE_TABLE_ROWS
    checks = check_expressions(
        table.run,
        table_sql=table.profile.table_sql,
        expressions={m["key"]: m["expression"] for m in mine},
        sample_size=None if whole else SAMPLE_SIZE,
    )
    for metric in mine:
        check = checks.get(metric["key"])
        if check is not None and check.ok:
            metric["evidence"] = {"value": check.value, "rows": rows if whole else table.profile.sample_rows, "whole_table": whole}
            continue
        result.metrics.remove(metric)
        reason = f"It did not run on the data: {check.error}" if check and check.error else "It did not run on the data."
        result.dropped.append({"type": "metric", "name": metric["name"], "table": table.profile.table, "expression": metric["expression"], "reason": reason})


def link_suggestions(
    links: LinksDraft,
    tables: dict[str, DraftTable],
    result: DraftResult,
    taken: dict[str, set[str]],
    *,
    join_check: Callable[..., JoinCheck | None] = check_join,
) -> None:
    by_name = {t.profile.table.lower(): t for t in tables.values()} | {k.lower(): t for k, t in tables.items()}
    for rel in links.relationships:
        left = by_name.get(rel.from_table.strip().lower())
        right = by_name.get(rel.to_table.strip().lower())
        label = f"{rel.from_table}.{rel.from_column} → {rel.to_table}.{rel.to_column}"
        if left is None or right is None or left is right:
            result.dropped.append({"type": "relationship", "name": label, "reason": "It does not join two of the selected tables."})
            continue
        from_col = left.profile.column(rel.from_column)
        to_col = right.profile.column(rel.to_column)
        if from_col is None or to_col is None:
            result.dropped.append({"type": "relationship", "name": label, "reason": "A column it names does not exist."})
            continue
        if left.connection_id != right.connection_id:
            result.dropped.append({"type": "relationship", "name": label, "reason": "The tables are in different data sources."})
            continue
        check = join_check(
            left.run,
            connector_type=left.profile.connector_type,
            from_table_sql=left.profile.table_sql,
            from_column=from_col.name,
            to_table_sql=right.profile.table_sql,
            to_column=to_col.name,
        )
        if check is None or check.checked == 0 or check.ratio < JOIN_CONFIRMED:
            found = f"{check.matched} of {check.checked}" if check and check.checked else "none"
            result.dropped.append({"type": "relationship", "name": label, "reason": f"The data does not confirm it: {found} sampled values were found on the other side."})
            continue
        key = unique(slug(f"{left.key}_to_{right.key}", "relationship"), taken["relationship"])
        result.relationships.append(
            {
                "suggestion_id": f"relationship:{key}",
                "key": key,
                "name": f"{left.profile.table} → {right.profile.table}",
                "description": rel.description.strip(),
                "from_entity_key": left.key,
                "to_entity_key": right.key,
                "join_expression": f"{left.key}.{from_col.name} = {right.key}.{to_col.name}",
                "relationship_type": "many_to_one",
                "evidence": {"matched": check.matched, "checked": check.checked},
                "status": "suggested",
            }
        )
    for term in links.terms[:MAX_TERMS]:
        if not term.term.strip() or not term.definition.strip():
            continue
        key = unique(slug(term.term, "term"), taken["term"])
        result.glossary_suggestions.append(
            {
                "suggestion_id": f"term:{key}",
                "key": key,
                "term": term.term.strip(),
                "name": term.term.strip(),
                "definition": term.definition.strip(),
                "synonyms": [s.strip() for s in term.synonyms if isinstance(s, str) and s.strip()][:4],
                # Not tied to metrics on purpose: a phrase that appears in many questions then pulls the wrong metric.
                "related_metric_keys": [],
                "status": "suggested",
            }
        )


def apply_headline(result: DraftResult, picks: list[HeadlinePick], tables: list[DraftTable]) -> None:
    """One ranking for the whole model (the overview leads with rank 1): the model's picks across tables when it made them, else
    each table's first pick in table order. A single table keeps its own ranking when no pick across tables was made."""
    def rank_of(metric: dict) -> int | None:
        return ((metric.get("metadata") or {}).get("reference_extension") or {}).get("headline")

    names = {t.key: {t.key.lower(), t.profile.table.lower()} for t in tables}
    chosen: list[dict] = []
    for pick in picks:
        table = pick.table.strip().lower()
        metric = next(
            (m for m in result.metrics if table in names.get(m["source_entity_key"], set()) and m["name"].strip().lower() == pick.metric.strip().lower()),
            None,
        )
        if metric is not None and metric not in chosen:
            chosen.append(metric)
    if not chosen:
        if len(tables) == 1:
            return
        firsts = []
        for table in tables:
            ranked = sorted((m for m in result.metrics if m["source_entity_key"] == table.key and rank_of(m)), key=rank_of)
            if ranked:
                firsts.append(ranked[0])
        chosen = firsts
    for metric in result.metrics:
        extension = (metric.get("metadata") or {}).get("reference_extension") or {}
        extension.pop("headline", None)
    for rank, metric in enumerate(chosen[:MAX_HEADLINE], start=1):
        metric.setdefault("metadata", {}).setdefault("reference_extension", {})["headline"] = rank
    for metric in result.metrics:
        if not (metric.get("metadata") or {}).get("reference_extension"):
            metric["metadata"] = {k: v for k, v in (metric.get("metadata") or {}).items() if k != "reference_extension"}


def disambiguate_names(items: list[dict], entity_names: dict[str, str]) -> None:
    """Two items of different tables with the same name ("Customer ID" in four tables) get the table's object in their name, so
    the reviewer and the resolver can tell them apart."""
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(str(item.get("name") or "").strip().lower(), []).append(item)
    for group in groups.values():
        if len({i["source_entity_key"] for i in group}) < 2:
            continue
        for item in group:
            owner = entity_names.get(item["source_entity_key"], item["source_entity_key"])
            item["name"] = f"{item['name']} ({owner})"


Progress = Callable[[str], None]


async def draft_model(
    provider: Any,
    tables: list[DraftTable],
    *,
    language: str = "en",
    context: str = "",
    provider_label: str = "",
    progress: Progress | None = None,
    concurrency: int = 3,
    join_check: Callable[..., JoinCheck | None] = check_join,
) -> DraftResult:
    """Draft the model for profiled tables. Each table is drafted and checked on its own, so one table the model cannot draft does
    not stop the others; the joins and terms come from a second call that sees every table."""
    say = progress or (lambda _message: None)
    result = DraftResult(provider=provider_label)
    taken: dict[str, set[str]] = {kind: set() for kind in ("dimension", "metric", "relationship", "term")}
    gate = asyncio.Semaphore(max(1, concurrency))
    done = 0

    async def one(table: DraftTable) -> TableDraft | None:
        nonlocal done
        async with gate:
            try:
                draft = await draft_table(provider, table, language=language, context=context)
            except Exception as exc:  # noqa: BLE001
                logger.warning("semantic_draft_table_failed table=%s error=%s", table.profile.table, type(exc).__name__)
                draft = None
            done += 1
            say(f"Drafted {done} of {len(tables)} table(s)")
            return draft

    say(f"Drafting {len(tables)} table(s) with {provider_label or 'the model'}")
    drafts = await asyncio.gather(*(one(t) for t in tables))
    drafted: list[tuple[DraftTable, TableDraft]] = []
    for table, draft in zip(tables, drafts):
        if draft is None:
            result.notes.append(f"The model could not draft {table.profile.table}; it is imported as a data model without metrics. Try again, or add them by hand.")
            draft = TableDraft(name=table.profile.table.replace("_", " ").title())
        table_suggestions(table, draft, result, taken)
        drafted.append((table, draft))

    say("Running every metric once on the data")
    for table in tables:
        await asyncio.to_thread(run_metric_checks, table, result)

    links = LinksDraft()
    if any(d.dimensions or d.metrics for _, d in drafted):
        say("Looking for joins, the headline and business terms")
        metric_names = {t.key: [m["name"] for m in result.metrics if m["source_entity_key"] == t.key] for t in tables}
        try:
            links = await draft_links(provider, drafted, language=language, context=context, metrics=metric_names)
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic_draft_links_failed error=%s", type(exc).__name__)
            result.notes.append("Joins and business terms could not be drafted; add them by hand if you need them.")
        if links.relationships:
            say("Checking joins against the data")
        by_key = {t.key: t for t in tables}
        await asyncio.to_thread(link_suggestions, links, by_key, result, taken, join_check=join_check)
    apply_headline(result, links.headline, tables)
    entity_names = {e["key"]: e["name"] for e in result.entities}
    disambiguate_names(result.dimensions, entity_names)
    disambiguate_names(result.metrics, entity_names)

    removed = clean_synonyms(result.dimensions + result.metrics)
    if removed:
        result.notes.append(f"{removed} synonym(s) shared by two items were removed so a question is not matched to the wrong one.")
    for profile in (t.profile for t in tables):
        result.notes.extend(f"{profile.table}: {note}" for note in profile.notes)
        if profile.skipped_columns:
            result.notes.append(f"{profile.table}: {len(profile.skipped_columns)} column(s) were left out (nested types or names that cannot be queried safely).")
        if profile.row_count and profile.row_count > profile.sample_rows > 0:
            result.notes.append(f"{profile.table}: profiled on the first {profile.sample_rows:,} of {profile.row_count:,} rows.")
    say("Done")
    return result

