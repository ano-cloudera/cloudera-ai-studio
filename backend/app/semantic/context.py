"""Semantic context of the published model: metric resolution and the governed SQL compiler."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
import os
import re

from app.core.config import get_settings
from app.semantic.registry import OssieRegistry


ROOT = Path(__file__).resolve().parents[2]
PROJECT_DIR = Path(os.environ.get("OSSIE_PROJECT_DIR") or ROOT / "projects" / "reference_impala")

_MONTH_WORDS = ("month", "bulan", "bulanan", "monthly", "by month", "per bulan", "trend", "tren", "12 bulan", "pertumbuhan")


def wants_by_month(question: str) -> bool:
    """A breakdown by month ("per bulan", "monthly", "trend"), not one month named with the word ("bulan Juni",
    "the month of June", "Juni bulan ini")."""
    from app.ask_data.intent_satisfaction import _MONTH_RE

    text = question.casefold()
    text = re.sub(rf"\b(bulan|month of|month)\s+({_MONTH_RE})\b", r"\2", text, flags=re.I)
    text = re.sub(r"\bbulan\s+(ini|lalu|kemarin|depan)\b", "", text)
    return any(term in text for term in _MONTH_WORDS)


def _table_key(name: str) -> str:
    """`"hive"."default"."orders"`, `hive.default.orders` and `HIVE.default.Orders` are the same table."""
    return name.replace('"', "").replace("`", "").strip().casefold()


@dataclass(frozen=True)
class TablePolicy:
    name: str
    domain: str
    columns: frozenset[str]
    time_columns: frozenset[str]
    description: str


def guidance_focus_from_metric(metric: str | None) -> str | None:
    """Kept for the capability menu: a published model has no fixed topics, so there is nothing to exclude."""
    return None


_BREAKDOWN_CUE = re.compile(r"\b(per|by|berdasarkan|breakdown|break down|each|setiap|masing|top\s+\d+)\b", re.IGNORECASE)


def _names_a_period(question: str) -> bool:
    """"kalau Juni?", "and in Q2 2026?": the same question for another period."""
    from app.ask_data.intent_satisfaction import parse_requested_constraints, parse_yearless_period

    try:
        return bool(parse_yearless_period(question) or parse_requested_constraints(question).explicit_period)
    except Exception:
        return False


def glossary_phrase_map(governance: dict[str, Any]) -> list[tuple[tuple[str, ...], str]]:
    """Business words the model author tied to a dimension in the glossary ("kurir" -> carrier)."""
    out: list[tuple[tuple[str, ...], str]] = []
    for entry in governance.get("glossary") or []:
        if not isinstance(entry, dict) or not entry.get("related_dimension_keys"):
            continue
        phrases = tuple(p for p in dict.fromkeys([str(entry.get("term") or "").strip(), *(str(s).strip() for s in entry.get("synonyms") or [])]) if p)
        if phrases:
            out.append((phrases, str(entry["related_dimension_keys"][0])))
    # Models published before the glossary moved here stored the same map under runtime_extensions.
    legacy = ((governance.get("runtime_extensions") or {}).get("breakdown") or {}).get("phrase_map") or []
    for item in legacy:
        if isinstance(item, dict) and item.get("dimension") and item.get("phrases"):
            out.append((tuple(str(p) for p in item["phrases"] if p), str(item["dimension"])))
    return out


class SemanticContextService:
    def __init__(self, project_dir: Path = PROJECT_DIR, *, validate_profile: bool = False) -> None:
        # Every model, published or the placeholder one, is read the same way. `validate_profile` is accepted for
        # callers that still pass it and only switches the registry's stricter checks.
        self._registry_runtime = True
        self.registry = OssieRegistry(project_dir, validate_profile=validate_profile)
        self.datasets = self.registry.datasets
        self.metrics = self.registry.metrics
        self._tables: dict[str, TablePolicy] = {}
        for dataset_name, dataset in self.datasets.items():
            fields = self.registry.dataset_fields[dataset_name]
            time_columns = {name for name, field in fields.items() if bool((field.get("dimension") or {}).get("is_time"))}
            column_names = {name.casefold() for name in fields}
            for field in fields.values():
                try:
                    column_names.add(self.registry.ansi_expression(field).casefold())
                except ValueError:
                    pass
            for metric in self.metrics.values():
                config = self.registry.metric_configs.get(metric["name"], {})
                if config.get("base_dataset") != dataset_name:
                    continue
                try:
                    expr = self.registry.ansi_expression(metric)
                except ValueError:
                    continue
                for token in re.findall(r"\b([a-z_][a-z0-9_]*)\b", expr, flags=re.IGNORECASE):
                    column_names.add(token.casefold())
            key = _table_key(str(dataset["source"]))
            self._tables[key] = TablePolicy(
                name=key,
                domain=dataset_name,
                columns=frozenset(column_names),
                time_columns=frozenset(time_columns),
                description=str(dataset.get("description") or ""),
            )

    @property
    def table_names(self) -> frozenset[str]:
        return frozenset(self._tables)

    def table_policy(self, name: str) -> TablePolicy:
        try:
            return self._tables[_table_key(name)]
        except KeyError as exc:
            raise ValueError(f"Table not allowed: {_table_key(name)}") from exc

    def _glossary_dimensions(self, question: str, allowed: set[str]) -> list[str]:
        if not allowed or not _BREAKDOWN_CUE.search(question):
            return []
        lowered = question.casefold()
        for phrases, dimension in glossary_phrase_map(self.registry.governance):
            if dimension in allowed and any(re.search(rf"\b{re.escape(p.casefold())}\b", lowered) for p in phrases):
                return [dimension]
        return []

    def _continue_previous_metric(self, question: str, previous: dict[str, Any] | None) -> dict[str, Any] | None:
        """A question that names no metric ("and per carrier?") keeps the metric of the previous turn.

        This is the safety net for when the language model could not rewrite the question; a rewritten question
        names its metric and never gets here."""
        if not previous:
            return None
        metric = previous.get("last_metric")
        if not isinstance(metric, str) or metric not in self.metrics:
            return None
        if self.registry.resolve_metric(question).get("status") == "resolved":
            return None
        definition = self.metric_definition(metric)
        allowed = set(definition.get("allowed_dimensions") or [])
        dataset = str(definition.get("base_dataset") or "")
        from app.ask_data.intent_satisfaction import infer_dimensions_from_question, pick_time_dimension

        named = self._glossary_dimensions(question, allowed) or infer_dimensions_from_question(
            question, allowed, dataset_name=dataset, registry=self.registry
        )
        dimensions = list(named)
        if wants_by_month(question):
            time_key = pick_time_dimension(dataset, allowed, self.registry) if dataset else None
            if time_key:
                # "per month" after a breakdown by carrier means by month: only what the question names stays.
                dimensions = [time_key, *[d for d in named if d != time_key]]
        if not dimensions and not _names_a_period(question):
            return None
        return {
            "status": "resolved",
            "metric": metric,
            "matched_alias": "session_metric_continuation",
            "definition": definition,
            "dimensions": list(dict.fromkeys(dimensions)),
            "dimension_mismatch": [],
        }

    def _resolve_registry_runtime(self, question: str, metric: str | None = None) -> dict[str, Any]:
        """Resolve a question to a governed metric, its breakdown and its period. With `metric` the metric is already
        chosen (by the language model, from the catalog) and only the rest is worked out."""
        from app.ask_data.intent_satisfaction import (
            dimension_display_name,
            parse_requested_constraints,
            unavailable_dimensions,
            validate_registry_resolution,
        )

        chosen_by_model = metric is not None
        if metric is not None:
            resolution: dict[str, Any] = {
                "status": "resolved",
                "metric": metric,
                "matched_alias": "model_choice",
                "definition": self.metric_definition(metric),
                "dimension_mismatch": [],
            }
        else:
            resolution = self.registry.resolve_metric(question)
        if resolution.get("status") == "resolved":
            metric = str(resolution["metric"])
            definition = self.metric_definition(metric)
            resolution.setdefault("definition", definition)
            allowed = set(definition.get("allowed_dimensions") or [])
            dimensions = list(resolution.get("dimensions") or [])
            if not dimensions and wants_by_month(question):
                from app.ask_data.intent_satisfaction import pick_time_dimension

                time_key = pick_time_dimension(str(definition["base_dataset"]), allowed, self.registry)
                if time_key:
                    dimensions = [time_key]
            if not dimensions:
                dimensions = self._glossary_dimensions(question, allowed)
            if not dimensions:
                from app.ask_data.intent_satisfaction import infer_dimensions_from_question

                dimensions = infer_dimensions_from_question(
                    question,
                    allowed,
                    dataset_name=str(definition["base_dataset"]),
                    registry=self.registry,
                )
            resolution["dimensions"] = dimensions
            resolution["dimension_mismatch"] = list(resolution.get("dimension_mismatch") or [])
            missing = unavailable_dimensions(question, allowed, dataset_name=str(definition["base_dataset"]), registry=self.registry)
            if missing:
                if not dimensions and not chosen_by_model:
                    other = self._alternative_metric(question, metric, missing)
                    if other:
                        return self._resolve_registry_runtime(question, metric=other)
                names = [dimension_display_name(self.registry, dataset, key) for key, dataset in missing]
                if not dimensions:
                    return self._unsupported_dimension(question, metric, definition, missing, names)
                resolution["dimension_mismatch"] = names
            constraints = parse_requested_constraints(question)
            if constraints.explicit_period:
                resolution["explicit_period"] = {
                    "year": constraints.explicit_period.year,
                    "month": constraints.explicit_period.month,
                }
            validation = validate_registry_resolution(
                question,
                resolution,
                definition=definition,
                registry=self.registry,
            )
            resolution["intent_validation"] = validation.as_metadata()
            if not validation.intent_complete:
                return {
                    "status": "needs_clarification",
                    "question": validation.user_message,
                    "reason": validation.reason_code,
                    "metric": metric,
                    "definition": definition,
                    "intent_validation": validation.as_metadata(),
                }
        return resolution

    def _supporting_metrics(self, wanted: set[str], *, skip: str) -> list[str]:
        return [
            name for name in self.metrics
            if name != skip and wanted <= set(self.metric_definition(name).get("allowed_dimensions") or [])
        ]

    def _alternative_metric(self, question: str, current: str, missing: list[tuple[str, str]]) -> str | None:
        """Another metric that can be broken down the way the question asks and that the question's other words point to
        ("pendapatan per loyalty tier": the revenue metric of the customer view, not the one of the transactions)."""
        from app.ask_data.intent_satisfaction import _dimension_labels
        from app.semantic.registry import _catalog_tokenize

        wanted = {key for key, _ in missing}
        candidates = self._supporting_metrics(wanted, skip=current)
        if not candidates:
            return None
        dimension_words = {tok for key, dataset in missing for label in _dimension_labels(self.registry, dataset, key) for tok in _catalog_tokenize(label)}
        tokens = {tok for tok in _catalog_tokenize(question) if len(tok) >= 4 and tok not in dimension_words}
        scored = sorted(
            ((sum(1 for tok in tokens if tok in " ".join(self.registry.metric_aliases(name)).casefold()), name) for name in candidates),
            key=lambda item: (-item[0], item[1]),
        )
        if not scored or scored[0][0] < 1 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
            return None
        return scored[0][1]

    def _unsupported_dimension(self, question: str, metric: str, definition: dict[str, Any], missing: list[tuple[str, str]], names: list[str]) -> dict[str, Any]:
        """Say plainly that the metric cannot be broken down that way, instead of answering with one number."""
        from app.ask_data.intent_satisfaction import dimension_display_name
        from app.ask_data.metric_labels import humanize_metric_label
        from app.core.language import detect_language

        label = humanize_metric_label(name=metric, definition=definition)
        dataset = str(definition.get("base_dataset") or "")
        offered = [dimension_display_name(self.registry, dataset, key) for key in definition.get("allowed_dimensions") or []][:8]
        others = [humanize_metric_label(name=name, definition=self.metric_definition(name)) for name in self._supporting_metrics({key for key, _ in missing}, skip=metric)][:3]
        if detect_language(question) == "id":
            text = f"{label} belum bisa dipecah per {' dan '.join(names)}."
            if offered:
                text += f" Metrik ini bisa dipecah per: {', '.join(offered)}."
            if others:
                text += f" Yang bisa dipecah per {' dan '.join(names)}: {', '.join(others)}."
        else:
            text = f"{label} cannot be broken down by {' and '.join(names)}."
            if offered:
                text += f" It can be broken down by: {', '.join(offered)}."
            if others:
                text += f" Metrics that can be broken down by {' and '.join(names)}: {', '.join(others)}."
        return {
            "status": "needs_clarification",
            "question": text,
            "reason": "unsupported_dimension",
            "metric": metric,
            "definition": definition,
            "intent_validation": {"intent_complete": False, "unresolved_constraints": [f"dimension:{key}" for key, _ in missing], "reason_code": "UNSUPPORTED_DIMENSION"},
        }

    def _registry_dimension_expression(self, dataset_name: str, dimension_key: str, question: str) -> str:
        field = self.registry.dataset_fields[dataset_name][dimension_key]
        base = self.registry.ansi_expression(field)
        if not re.match(r"^d\.", base.strip(), flags=re.IGNORECASE):
            base = f"d.{base}"
        from app.ask_data.intent_satisfaction import pick_time_dimension

        is_date_column = (field.get("dimension") or {}).get("is_time") or dimension_key == pick_time_dimension(
            dataset_name, {dimension_key}, self.registry
        )
        if is_date_column and wants_by_month(question):
            return f"DATE_TRUNC('month', CAST({base} AS TIMESTAMP))"
        return base

    def _compile_registry_governed(
        self,
        metric: str,
        question: str,
        requested_dimensions: list[str] | None = None,
        extra_predicates: list[str] | None = None,
        *,
        company_total_aggregate: bool = False,
        from_source: str | None = None,
    ) -> str:
        definition = self.metric_definition(metric)
        dataset_name = definition["base_dataset"]
        dataset = self.datasets[dataset_name]
        allowed = set(definition["allowed_dimensions"])
        from app.ask_data.intent_satisfaction import registry_period_sql_predicate
        from app.core.config import get_settings

        period_predicate = registry_period_sql_predicate(
            question,
            dataset_name=dataset_name,
            registry=self.registry,
        )
        if company_total_aggregate:
            dimensions: list[str] = []
        elif requested_dimensions is not None:
            dimensions = [d for d in requested_dimensions if d in allowed]
        else:
            dimensions = []
            if wants_by_month(question):
                from app.ask_data.intent_satisfaction import pick_time_dimension

                time_key = pick_time_dimension(dataset_name, allowed, self.registry)
                if time_key:
                    dimensions = [time_key]
            if not dimensions:
                dimensions = self._glossary_dimensions(question, allowed)
            if not dimensions:
                from app.ask_data.intent_satisfaction import infer_dimensions_from_question

                dimensions = infer_dimensions_from_question(
                    question, allowed, dataset_name=dataset_name, registry=self.registry
                )
        dimensions = list(dict.fromkeys(dimensions))
        if any(name not in allowed for name in dimensions):
            raise ValueError("Requested dimension is not governed for this metric")
        expression = definition["expression"].replace(f"{dataset_name}.", "d.")
        dim_exprs = [
            self._registry_dimension_expression(dataset_name, name, question) for name in dimensions
        ]
        projections = [f"{expr} AS {name}" for expr, name in zip(dim_exprs, dimensions)]
        projections.append(f"{expression} AS metric_value")
        predicates: list[str] = []
        if definition.get("row_filter"):
            predicates.append(f"({definition['row_filter']})")
        if period_predicate:
            predicates.append(period_predicate)
        if extra_predicates:
            predicates.extend(extra_predicates)
        source = from_source or dataset["source"]
        sql = ["SELECT", "  " + ",\n  ".join(projections), f"FROM {source} d"]
        if predicates:
            sql.append("WHERE " + "\n  AND ".join(predicates))
        if dim_exprs:
            sql.append("GROUP BY " + ", ".join(dim_exprs))
        from app.ask_data.intent_satisfaction import requested_sort_direction

        by_month = wants_by_month(question) and any(expr.startswith("DATE_TRUNC('month'") for expr in dim_exprs)
        if by_month:
            sql.append("ORDER BY " + ", ".join(expr for expr in dim_exprs if expr.startswith("DATE_TRUNC('month'")) + " ASC")
        else:
            sql.append(f"ORDER BY metric_value {requested_sort_direction(question)}")
        sql.append(f"LIMIT {get_settings().sql_max_rows}")
        return "\n".join(sql)


    def resolve(
        self,
        question: str,
        session_last_metric: str | None = None,
        session_analysis_context: dict[str, Any] | None = None,
        turn_understanding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve a question to a governed metric. `session_analysis_context` is the previous turn
        ({"last_metric", "last_dimensions"}); `session_last_metric` and `turn_understanding` are accepted for old
        callers and not used."""
        continued = self._continue_previous_metric(question, session_analysis_context)
        if continued is not None:
            return continued
        return self._resolve_registry_runtime(question)

    def resolve_for_metric(self, question: str, metric: str) -> dict[str, Any]:
        """The resolution of `question` with its metric chosen elsewhere; a metric the model does not have is an
        error rather than a silent switch."""
        if metric not in self.metrics:
            raise KeyError(metric)
        return self._resolve_registry_runtime(question, metric)

    def metric_definition(self, metric: str) -> dict[str, Any]:
        return self.registry.metric_definition(metric)

    def compile_governed(
        self,
        metric: str,
        question: str,
        requested_dimensions: list[str] | None = None,
        extra_predicates: list[str] | None = None,
        *,
        company_total_aggregate: bool = False,
        from_source: str | None = None,
    ) -> str:
        return self._compile_registry_governed(
            metric,
            question,
            requested_dimensions,
            extra_predicates,
            company_total_aggregate=company_total_aggregate,
            from_source=from_source,
        )

    def planner_context(self, domains: list[str] | None = None) -> dict[str, Any]:
        selected = {domain for domain in domains or [] if domain in self.datasets} or set(self.datasets)
        datasets = []
        for name in sorted(selected):
            dataset = self.datasets[name]
            policy = self.table_policy(dataset["source"])
            datasets.append({
                "name": name,
                "view": policy.name,
                "description": policy.description,
                "columns": sorted(policy.columns),
                "time_columns": sorted(policy.time_columns),
            })
        metrics = []
        for name in sorted(self.metrics):
            definition = self.metric_definition(name)
            if definition["base_dataset"] in selected:
                metrics.append({
                    "name": name,
                    "description": definition["description"],
                    "dataset": definition["base_dataset"],
                    "dimensions": definition["allowed_dimensions"],
                })
        payload: dict[str, Any] = {
            "authority": "Published semantic model",
            "datasets": datasets,
            "metrics": metrics,
            "relationships": [],
            "join_policy": "No runtime joins; use only published cross-domain views.",
        }
        return payload

    def greeting_context(self) -> dict[str, Any]:
        from app.ask_data.capability_catalog import resolve_capability_insight_lines, resolve_example_questions

        summary = self.registry.capability_summary()
        settings = get_settings()
        return {
            "scope": summary.get("scope") or "Published semantic model",
            "domains": sorted({str(d) for d in self.datasets}),
            "examples": resolve_example_questions(self, limit=4, settings=settings),
            "domain_options": [],
            "domain_capability_lines": resolve_capability_insight_lines(self, limit=8, settings=settings),
            "dataset_count": len(self.datasets),
            "metric_count": len(self.metrics),
        }

    def domain_capability_insight_lines(
        self,
        *,
        exclude_focus: str | None = None,
        configured_starters: list[str] | None = None,
        settings: Any | None = None,
        limit: int = 6,
        language: str = "en",
    ) -> list[str]:
        from app.ask_data.capability_catalog import resolve_capability_insight_lines

        return resolve_capability_insight_lines(
            self,
            configured_starters=configured_starters,
            exclude_focus=exclude_focus,
            limit=limit,
            settings=settings or get_settings(),
            language=language,
        )


    def guidance_context(self, question: str, *, configured_starters: list[str] | None = None, **_: Any) -> dict[str, Any]:
        from app.core.language import detect_language

        return {
            **self.greeting_context(),
            "focus": None,
            "excluded_focus": None,
            "metrics": [
                {"name": name, "description": d["description"], "dimensions": d["allowed_dimensions"]}
                for name in sorted(self.metrics)
                if (d := self.metric_definition(name))
            ][:40],
            "domain_capability_lines": self.domain_capability_insight_lines(
                configured_starters=configured_starters, language=detect_language(question)
            ),
        }


@lru_cache(maxsize=1)
def get_semantic_context() -> SemanticContextService:
    return SemanticContextService()
