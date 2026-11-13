from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.language import detect_language


def _normalize(value: str) -> str:
    return re.sub(r"[\s_\-.,!?;:'\"/]+", "", value).casefold()


# Words that carry no metric-identifying meaning on their own (Indonesian and English function words and generic
# question phrasing), excluded from token-overlap matching so a common word does not cause spurious matches.
_STOPWORDS = frozenset({
    "yang", "dengan", "dan", "atau", "untuk", "dari", "pada", "ini", "itu",
    "mana", "apa", "apakah", "bagaimana", "berapa", "adalah", "the", "a",
    "an", "of", "for", "with", "and", "or", "is", "are", "value", "nilai",
    "per", "each", "setiap", "total", "jumlah",
})


def _tokenize(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if word and word not in _STOPWORDS}


# Metric matching keeps "total"/"jumlah" so that "total amount" style questions still match their alias.
_CATALOG_STOPWORDS = _STOPWORDS - frozenset({"total", "jumlah"})


def _catalog_tokenize(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if word and word not in _CATALOG_STOPWORDS}


def _stems(tokens: set[str]) -> set[str]:
    """Singular forms, so that "order" finds the alias "orders"."""
    return {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in tokens}




def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" or isinstance(value, bool) else float(value)
    except (TypeError, ValueError):
        return None

class OssieRegistry:
    """Read-only registry of one published Apache Ossie semantic model."""

    def __init__(self, project_dir: Path, *, validate_profile: bool = True):
        self.project_dir = project_dir.resolve()
        self.model_path = self.project_dir / "ossie" / "reference_core.ossie.yaml"
        self.governance_path = self.project_dir / "ossie" / "reference_governance.yaml"
        self.golden_path = self.project_dir / "ossie" / "golden_questions.yaml"

        self.model = self._load(self.model_path)
        self.governance = self._load(self.governance_path)
        self.golden_questions = self._load(self.golden_path)
        self.datasets = {item["name"]: item for item in self.model.get("datasets", [])}
        self.metrics = {item["name"]: item for item in self.model.get("metrics", [])}
        self.dataset_fields = {
            name: {field["name"]: field for field in dataset.get("fields", [])}
            for name, dataset in self.datasets.items()
        }
        self.metric_configs = {name: self.reference_extension(metric) for name, metric in self.metrics.items()}
        self.runtime_extensions = None  # kept for callers that still look; published models carry no demo profile
        if validate_profile:
            self.validate()
        else:
            self._validate_minimal()

    def _validate_minimal(self) -> None:
        errors: list[str] = []
        if not self.datasets:
            errors.append("No datasets in OSSIE artifact")
        if not self.metrics:
            errors.append("No metrics in OSSIE artifact")
        if errors:
            raise ValueError("Invalid OSSIE registry:\n- " + "\n- ".join(errors))

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"Expected YAML object in {path}")
        return value

    @staticmethod
    def reference_extension(item: dict[str, Any]) -> dict[str, Any]:
        for extension in item.get("custom_extensions", []):
            if extension.get("vendor_name") != "REFERENCE":
                continue
            data = extension.get("data", {})
            return json.loads(data) if isinstance(data, str) else dict(data)
        return {}

    @staticmethod
    def ansi_expression(item: dict[str, Any]) -> str:
        expression = item.get("expression", {})
        if isinstance(expression, str):
            return expression
        for candidate in expression.get("dialects", []):
            if candidate.get("dialect") == "ANSI_SQL":
                return str(candidate["expression"])
        raise ValueError(f"No ANSI_SQL expression for {item.get('name')}")


    def validate(self) -> None:
        errors: list[str] = []
        if not self.model.get("name"):
            errors.append("Ossie model has no name")
        if self.model.get("relationships"):
            errors.append("Runtime joins are disabled for Semantic Contract v1")
        for dataset_name, dataset in self.datasets.items():
            fields = self.dataset_fields[dataset_name]
            for key in dataset.get("primary_key", []):
                if key not in fields:
                    errors.append(f"{dataset_name} primary key references unknown field {key}")
        for metric_name in self.metrics:
            config = self.metric_configs[metric_name]
            dataset_name = config.get("base_dataset")
            if dataset_name not in self.datasets:
                errors.append(f"{metric_name} has invalid base_dataset {dataset_name}")
                continue
            dimensions = {name for name, field in self.dataset_fields[dataset_name].items() if "dimension" in field}
            unknown = set(config.get("allowed_dimensions", [])) - dimensions
            if unknown:
                errors.append(f"{metric_name} has unknown dimensions {sorted(unknown)}")
        if errors:
            raise ValueError("Invalid Ossie registry:\n- " + "\n- ".join(errors))

    def metric_aliases(self, metric_name: str) -> list[str]:
        metric = self.metrics[metric_name]
        context = metric.get("ai_context", {})
        values = [metric_name, metric_name.replace("_", " "), metric.get("description", "")]
        if isinstance(context, dict):
            if context.get("display_name"):
                values.append(str(context["display_name"]))
            values.extend(context.get("synonyms", []))
        return [str(value) for value in values if value]

    def _metric_picker_clarification(self, question: str) -> dict[str, Any]:
        from app.ask_data.metric_labels import humanize_metric_label

        normalized = _normalize(question)
        scored: list[tuple[int, str]] = []
        for metric_name in self.metrics:
            score = 0
            label_blob = " ".join(self.metric_aliases(metric_name)).casefold()
            for tok in _catalog_tokenize(question):
                if len(tok) >= 4 and tok in label_blob:
                    score += 40
            for alias in self.metric_aliases(metric_name):
                if _normalize(alias) in normalized:
                    score += 100
            scored.append((max(score, 1), metric_name))
        scored.sort(reverse=True)
        options: list[dict[str, str]] = []
        for _, metric_name in scored[:4]:
            label = humanize_metric_label(name=metric_name, definition=self.metric_definition(metric_name))
            options.append({"type": "semantic_metric", "id": metric_name, "name": label})
        return {
            "status": "needs_clarification",
            "reason": "metric_ambiguous",
            "question": self.governance.get(
                "unknown_metric_question",
                "Metrik mana yang ingin Anda lihat? Pilih salah satu metric yang terdaftar di semantic layer."
                if detect_language(question) == "id"
                else "Which metric would you like to report on? Pick one of the metrics registered in the semantic layer.",
            ),
            "options": options,
        }

    def _resolve_semantic_registry_catalog_metric(self, question: str) -> dict[str, Any]:
        normalized = _normalize(question)
        question_tokens = _catalog_tokenize(question)
        candidates: list[tuple[int, str, str]] = []
        for metric_name in self.metrics:
            score = 0
            matched_alias = metric_name
            for alias in self.metric_aliases(metric_name):
                normalized_alias = _normalize(alias)
                alias_tokens = _catalog_tokenize(alias)
                if normalized_alias and normalized_alias in normalized:
                    score = max(score, 200 + len(normalized_alias))
                    matched_alias = alias
                elif (
                    alias_tokens
                    and len(alias_tokens) >= len(set(re.findall(r"[a-z0-9]+", alias.casefold())))  # not shortened by the tokenizer
                    and (alias_tokens <= question_tokens or _stems(alias_tokens) <= _stems(question_tokens))
                ):
                    score = max(score, 120 + len(alias_tokens))  # "order" and "orders" are the same word here
                    matched_alias = alias
                elif len(alias_tokens) == 1 and alias_tokens <= question_tokens:
                    token = next(iter(alias_tokens))
                    if len(token) >= 4:
                        score = max(score, 80 + len(token))
                        matched_alias = alias
            if score > 0:
                candidates.append((score, metric_name, matched_alias))
        if not candidates:
            return self._metric_picker_clarification(question)
        candidates.sort(reverse=True)
        top_score, metric_name, alias = candidates[0]
        runner_up = candidates[1][0] if len(candidates) > 1 else 0
        if len(candidates) > 1 and top_score - runner_up < 25:
            return self._metric_picker_clarification(question)
        return {
            "status": "resolved",
            "metric": metric_name,
            "matched_alias": alias,
            "definition": self.metric_definition(metric_name),
            "dimension_mismatch": [],
        }

    def resolve_ambiguity(self, question: str) -> dict[str, Any] | None:
        """Ambiguities the model author declared in the governance file (trigger terms and options)."""
        normalized = _normalize(question)
        for ambiguity in self.governance.get("ambiguities", []) or []:
            if not any(_normalize(str(term)) in normalized for term in ambiguity.get("trigger_terms", [])):
                continue
            selected = [
                option
                for option in ambiguity.get("options", [])
                if any(_normalize(str(term)) in normalized for term in option.get("discriminators", []))
            ]
            if len(selected) == 1:
                return None
            return {
                "status": "needs_clarification",
                "reason": ambiguity["name"],
                "question": ambiguity["question"],
                "options": ambiguity.get("options", []),
            }
        return None

    def resolve_metric(self, question: str) -> dict[str, Any]:
        ambiguity = self.resolve_ambiguity(question)
        if ambiguity:
            return ambiguity
        return self._resolve_semantic_registry_catalog_metric(question)

    def metric_catalog_for_classification(self) -> list[dict[str, Any]]:
        """Closed list of {name, description, allowed_dimensions} for every governed metric, for steps where a
        language model picks a metric. allowed_dimensions lets it tell apart two metrics with similar descriptions."""
        result = []
        for name, metric in self.metrics.items():
            config = self.metric_configs.get(name, {})
            result.append(
                {
                    "name": name,
                    "description": str(metric.get("description") or ""),
                    "allowed_dimensions": config.get("allowed_dimensions", []),
                    "headline": int(config.get("headline") or 0),  # 1 is the metric the business watches most; 0 is not a headline
                    # Declared by the model's author for Home: which way is good ("up", "down" or none) and a target, if any.
                    "better": config.get("better") if config.get("better") in ("up", "down") else None,
                    "target": _number(config.get("target")),
                }
            )
        return result

    def metric_definition(self, metric_name: str) -> dict[str, Any]:
        if metric_name not in self.metrics:
            raise KeyError(metric_name)
        metric = self.metrics[metric_name]
        config = self.metric_configs[metric_name]
        return {
            "name": metric_name,
            "metric_id": config.get("metric_id"),
            "description": metric.get("description"),
            "expression": self.ansi_expression(metric),
            "datatype": metric.get("datatype"),
            "base_dataset": config.get("base_dataset"),
            "allowed_dimensions": config.get("allowed_dimensions", []),
            "required_filters": config.get("required_filters", []),
            "row_filter": config.get("row_filter"),
            "governance_status": config.get("governance_status"),
            "business_approval_status": config.get("business_approval_status"),
            "original_kpi_id": config.get("original_kpi_id"),
            "unit_format": config.get("unit_format"),
            "unit": config.get("unit"),
            "ai_context": metric.get("ai_context", {}),
        }

    def capability_summary(self) -> dict[str, Any]:
        return {
            "model": self.model["name"],
            "scope": self.governance.get("scope", {}),
            "datasets": [
                {
                    "name": name,
                    "description": dataset.get("description"),
                    "source": dataset.get("source"),
                }
                for name, dataset in self.datasets.items()
            ],
            "metrics": [
                self.metric_definition(metric_name) for metric_name in self.metrics
            ],
            "examples": [
                item["question"]
                for item in self.golden_questions.get("questions", [])
                if item.get("expected_status") in {"supported", "supported_with_caveat"}
            ][:8],
        }

