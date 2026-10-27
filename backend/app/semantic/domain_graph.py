"""Load TEMPO domain business graph (YAML) for disambiguation and inquiry context."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

CabangGrain = Literal["sales_office", "branch", "ambiguous"]

_GRAPH_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "tempo_domain_graph.yaml"
_OFFICE_CODE_RE = re.compile(r"\b(0\d{3})\b")


@lru_cache(maxsize=1)
def load_domain_graph(path: Path | None = None) -> dict[str, Any]:
    graph_path = path or _GRAPH_PATH
    raw = graph_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid domain graph: {graph_path}")
    return data


def _normalized_terms(text: str) -> str:
    return " ".join(text.casefold().replace("–", "-").split())


def detect_domain_ids(question: str) -> list[str]:
    """Return domain ids mentioned or implied by the question."""
    graph = load_domain_graph()
    lowered = _normalized_terms(question)
    found: list[str] = []
    for domain in graph.get("domains") or []:
        if not isinstance(domain, dict):
            continue
        domain_id = str(domain.get("id") or "")
        label = str(domain.get("label") or "").casefold()
        if domain_id and domain_id.replace("_", " ") in lowered:
            found.append(domain_id)
        elif label and label in lowered:
            found.append(domain_id)
    keyword_map = {
        "sales": ("sell-in", "sell in", "penjualan tempo", "gross billing", "gross sales"),
        "b2b": ("sell-out", "sell out", "b2b", "partner ke konsumen", "alfamart", "penjualan alfamart"),
        "stock_tempo": ("stok tempo", "stock tempo", "gudang tempo"),
        "stock_sat": ("stok dc", "stok store", "stok alfamart", "sat-idm", "sat idm"),
        "sat_oos": ("oos", "out of stock", "kehabisan"),
        "service_level": ("fill rate", "service level", "services level", "fillrate", "tingkat layanan"),
        "picking": ("picking",),
        "unloading": ("unloading",),
        "promo": ("promo", "roi promo", "mekanisme promo"),
    }
    for domain_id, terms in keyword_map.items():
        if domain_id not in found and any(term in lowered for term in terms):
            found.append(domain_id)
    return list(dict.fromkeys(found))


def classify_cabang_grain(
    question: str,
    *,
    session_last_metric: str | None = None,
) -> CabangGrain:
    """Disambiguate Indonesian 'cabang' between Sell-In sales office vs B2B branch."""
    graph = load_domain_graph()
    disambig = (graph.get("disambiguation") or {}).get("cabang") or {}
    lowered = _normalized_terms(question)

    if not re.search(r"\b(branch|cabang|branches|sales\s+office)\b", lowered):
        return "ambiguous"

    sell_in_terms = tuple(disambig.get("prefer_sales_office", {}).get("terms") or ())
    sell_out_terms = tuple(disambig.get("prefer_branch", {}).get("terms") or ())

    has_in = any(term in lowered for term in sell_in_terms)
    has_out = any(term in lowered for term in sell_out_terms)

    if session_last_metric:
        metric = session_last_metric.casefold()
        if "sales_office" in metric or "sales_off" in metric:
            has_in = True
        if "b2b_branch" in metric or "branch_sell_out" in metric:
            has_out = True

    if has_in and not has_out:
        return "sales_office"
    if has_out and not has_in:
        return "branch"
    if has_in and has_out:
        return "ambiguous"
    default = str(disambig.get("default_grain") or "sales_office")
    if default == "branch":
        return "branch"
    return "sales_office"


def journey_for_domains(from_domain: str, to_domain: str) -> dict[str, Any] | None:
    graph = load_domain_graph()
    for journey in graph.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        if journey.get("from_domain") == from_domain and journey.get("to_domain") == to_domain:
            return journey
    return None


def _terms_match(lowered: str, terms: list[str], *, mode: str) -> bool:
    if not terms:
        return mode != "all"
    if mode == "all":
        return all(str(term).casefold() in lowered for term in terms)
    return any(str(term).casefold() in lowered for term in terms)


def _clarification_match_text(question: str) -> str:
    """After a chip reply, match dual-metric rules on the choice line only."""
    lowered = _normalized_terms(question)
    marker = "klarifikasi pengguna:"
    if marker in lowered:
        return lowered.split(marker, 1)[1].strip()
    return lowered


def try_clarification_intent(question: str) -> dict[str, Any] | None:
    """Return needs_clarification when domain graph detects dual-metric questions."""
    graph = load_domain_graph()
    lowered = _normalized_terms(question)
    match_text = _clarification_match_text(question)
    for intent in graph.get("clarification_intents") or []:
        if not isinstance(intent, dict):
            continue
        all_terms = intent.get("all_terms") or []
        unless = intent.get("unless_terms") or []
        if unless and _terms_match(lowered, list(unless), mode="any"):
            continue
        if all_terms and not _terms_match(match_text, list(all_terms), mode="all"):
            continue
        any_terms = intent.get("any_terms") or []
        if any_terms and not _terms_match(lowered, list(any_terms), mode="any"):
            continue
        if not all_terms and not any_terms:
            continue
        options = intent.get("options") or []
        if not isinstance(options, list) or not options:
            continue
        return {
            "status": "needs_clarification",
            "reason": str(intent.get("reason") or intent.get("id") or "domain_graph_clarification"),
            "question": str(intent.get("question") or "Pilih metrik yang dimaksud.").strip(),
            "options": options,
        }
    return None


def try_governed_intent_route(
    question: str,
    *,
    session_last_metric: str | None = None,
) -> dict[str, Any] | None:
    """Return OSSIE metric/dimensions when domain graph intent rules match."""
    graph = load_domain_graph()
    lowered = _normalized_terms(question)
    eval_text = _clarification_match_text(question) if "klarifikasi pengguna:" in lowered else lowered
    if session_last_metric:
        metric = session_last_metric.casefold()
        if "sell_out" in metric or "b2b_branch" in metric:
            eval_text = f"{eval_text} sell-out"
        elif "sell_in" in metric or "sales_office" in metric or "material_sell_in" in metric:
            eval_text = f"{eval_text} sell-in"

    for intent in graph.get("governed_intents") or []:
        if not isinstance(intent, dict):
            continue
        unless = intent.get("unless_terms") or []
        if _terms_match(eval_text, list(unless), mode="any"):
            continue
        all_terms = intent.get("all_terms") or []
        any_terms = intent.get("any_terms") or []
        if all_terms and not _terms_match(eval_text, list(all_terms), mode="all"):
            continue
        if any_terms and not _terms_match(eval_text, list(any_terms), mode="any"):
            continue
        if not any_terms and not all_terms:
            continue
        metric = intent.get("metric")
        if not isinstance(metric, str) or not metric:
            continue
        dimensions = intent.get("dimensions")
        if not isinstance(dimensions, list):
            dimensions = []
        return {
            "metric": metric,
            "dimensions": [str(item) for item in dimensions],
            "matched_alias": str(intent.get("resolved_by") or intent.get("id") or "domain_graph_intent"),
        }
    return None


def intent_hints(question: str) -> dict[str, Any]:
    """Deterministic hints from intent_routes (metric/dimension suggestions)."""
    graph = load_domain_graph()
    lowered = _normalized_terms(question)
    for route in graph.get("intent_routes") or []:
        if not isinstance(route, dict):
            continue
        terms = route.get("match_terms") or []
        if any(str(term).casefold() in lowered for term in terms):
            return {
                "primary_domain": route.get("primary_domain"),
                "metric_hint": route.get("metric_hint"),
                "dimension_hint": route.get("dimension_hint"),
            }
    return {}


def build_business_context(
    question: str,
    *,
    session_last_metric: str | None = None,
) -> dict[str, Any]:
    """Snapshot for inquiry_brief / planner (no SQL)."""
    domains = detect_domain_ids(question)
    cabang = classify_cabang_grain(question, session_last_metric=session_last_metric)
    journey: dict[str, Any] | None = None
    if len(domains) >= 2:
        journey = journey_for_domains(domains[0], domains[1])
    hints = intent_hints(question)
    office_codes = sorted(set(_OFFICE_CODE_RE.findall(question)))
    graph = load_domain_graph()
    partner_scope = None
    lowered = _normalized_terms(question)
    scope_block = graph.get("partner_scope") if isinstance(graph.get("partner_scope"), dict) else {}
    if "b2b" in domains or "alfamart" in lowered or any(t in lowered for t in ("sell-out", "sell out", "b2b")):
        alf = scope_block.get("alfamart")
        if isinstance(alf, dict):
            partner_scope = alf
    return {
        "scope": graph.get("scope"),
        "join_policy": graph.get("join_policy"),
        "detected_domains": domains,
        "cabang_grain": cabang,
        "journey": journey,
        "intent_hints": hints or None,
        "office_codes": office_codes,
        "partner_scope": partner_scope,
    }
