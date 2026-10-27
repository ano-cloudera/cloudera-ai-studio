"""Cross-domain analytic follow-ups: analysis context, entity binding, drill plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.semantic.domain_graph import classify_cabang_grain
from app.services.session_context import (
    _last_governed_chart_turn,
    _last_governed_success_turn,
    _ranked_entities_from_rows,
    _rows_for_chart_follow_up,
    infer_governed_metric_from_turn,
)

from app.services.conversational import TurnUnderstanding

_TOP_N_RE = re.compile(r"\btop\s*(\d+)\b", re.IGNORECASE)
_RANK_N_RE = re.compile(r"\b(?:rank|urutan|no\.?)\s*(\d+)\b", re.IGNORECASE)
_MATERIAL_CODE_RE = re.compile(r"\b(FE\d+)\b", re.IGNORECASE)
_COMPARE_PAIR_RE = re.compile(
    r"\burutan\s*(\d+)\s*(?:dan|dengan|vs|&|serta)\s*urutan\s*(\d+)\b",
    re.IGNORECASE,
)
_RELIMIT_RE = re.compile(
    r"\b(?:hanya|tampilkan)\s*(?:top\s*)?(\d+)\s*saja\b",
    re.IGNORECASE,
)


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

_DRILL_MATERIAL_TERMS = (
    "produk",
    "product",
    "material",
    "sku",
    "plu",
    "item",
    "breakdown",
    "break down",
    "rincian",
    "detail",
)

_FILTER_TERMS = ("based on", "berdasarkan", "untuk", "for", "di ", "cabang", "branch", "dc ")

# metric prefix / name → (domain_id, default grain column)
_METRIC_DOMAIN_GRAIN: dict[str, tuple[str, str]] = {
    "b2b_branch_sell_out": ("b2b", "branch"),
    "b2b_branch_material": ("b2b", "branch"),
    "b2b_branch": ("b2b", "branch"),
    "material_sell_out": ("b2b", "material"),
    "b2b_material": ("b2b", "material"),
    "material_sell_in": ("sales", "material"),
    "sales_office_material": ("sales", "material"),
    "sales_office_sell_in": ("sales", "sales_office"),
    "sales_office": ("sales", "sales_office"),
    "sat_dc_stock": ("stock_sat", "dcname"),
    "sat_store_stock": ("stock_sat", "division"),
    "sat_oos": ("sat_oos", "material_code"),
    "service_fill_rate": ("service_level", "sales_off"),
    "sales_office_service": ("service_level", "sales_off"),
    "sales_office_service_unfulfilled": ("service_level", "sales_off"),
    "average_picking": ("picking", "sales_off"),
    "average_unloading": ("unloading", "sales_off"),
    "promo_": ("promo", "material"),
    "warehouse_stock": ("stock_tempo", "material"),
    "stock_tempo": ("stock_tempo", "material"),
}


def infer_domain_and_grain(metric: str | None, entity_dimension: str | None) -> tuple[str | None, str | None]:
    if not metric:
        return None, entity_dimension
    lowered = metric.casefold()
    if "unfulfilled" in lowered or "service_fill_rate" in lowered or lowered.startswith("service_fill"):
        grain = entity_dimension or ("sales_off" if "office" in lowered or "sales_off" in lowered else None)
        return "service_level", grain
    for prefix, (domain_id, grain) in _METRIC_DOMAIN_GRAIN.items():
        if prefix in lowered:
            return domain_id, entity_dimension or grain
    return None, entity_dimension


def build_analysis_context(
    *,
    metric: str | None,
    dimensions: list[str] | None,
    entity_dimension: str | None,
    ranked_entities: list[dict[str, Any]],
    last_question: str,
) -> dict[str, Any]:
    domain_id, grain = infer_domain_and_grain(metric, entity_dimension)
    catalog: list[dict[str, Any]] = []
    for item in ranked_entities:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        dim = str(item.get("dimension") or grain or "entity")
        catalog.append(
            {
                "rank": item.get("rank"),
                "entity_type": dim,
                "id": str(item["id"]),
                "display": str(item["id"]),
                "metric_value": item.get("metric_value"),
            }
        )
    return {
        "domain_id": domain_id,
        "last_metric": metric,
        "last_dimensions": list(dimensions or []),
        "active_grain": grain,
        "entity_dimension": entity_dimension,
        "result_catalog": catalog,
        "last_question": last_question.strip(),
        "time_scope": "Q4_2024",
    }


def analysis_context_from_history(history: list[dict]) -> dict[str, Any]:
    anchor = (
        _last_governed_chart_turn(history)
        or _last_governed_success_turn(history)
        or (history[-1] if history else None)
    )
    if not anchor:
        return {}
    stored = anchor.get("session_frame") if isinstance(anchor.get("session_frame"), dict) else {}
    ctx = stored.get("analysis_context")
    if isinstance(ctx, dict) and ctx.get("last_metric"):
        return ctx
    metric = stored.get("last_metric")
    ranked = list(stored.get("ranked_entities") or [])
    stored_dims = list(stored.get("last_dimensions") or [])
    if not ranked:
        ranked = _ranked_entities_from_rows(
            _rows_for_chart_follow_up(anchor),
            preferred_dimensions=stored_dims,
        )
    if not metric:
        metric = infer_governed_metric_from_turn(anchor, ranked_entities=ranked)
    if not metric and not ranked:
        return {}
    entity_dimension = stored.get("entity_dimension")
    if not entity_dimension and ranked:
        entity_dimension = ranked[0].get("dimension")
    return build_analysis_context(
        metric=str(metric) if metric else None,
        dimensions=list(stored.get("last_dimensions") or []),
        entity_dimension=str(entity_dimension) if entity_dimension else None,
        ranked_entities=ranked,
        last_question=str(stored.get("last_question") or anchor.get("question") or ""),
    )


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("–", "-").split())


def _parse_top_n(question: str, default: int = 5) -> int:
    match = _TOP_N_RE.search(question)
    if match:
        return max(1, min(25, int(match.group(1))))
    return default


_TIME_GRAIN_TERMS = (
    "per bulan",
    "perbulan",
    "perbulannya",
    "bulanan",
    "per month",
    "monthly",
    "tren",
    "trend",
)


def _wants_monthly_time_breakdown(question: str) -> bool:
    lowered = _normalize(question)
    return any(term in lowered for term in _TIME_GRAIN_TERMS)


def _wants_prior_top_entity_focus(question: str) -> bool:
    lowered = _normalize(question)
    return any(
        t in lowered
        for t in (
            "paling tinggi",
            "tertinggi",
            "terbesar",
            "terbanyak",
            "paling atas",
            "teratas",
            "rank 1",
            "urutan 1",
            "top 1",
            "material itu",
            "produk itu",
            "produk/material itu",
            "material tersebut",
            "produk tersebut",
            "yang tadi",
            "tadi",
            "tersebut",
            "cabang itu",
            "dc itu",
            "office itu",
            "sales office itu",
            "partner itu",
            "paling lambat",
            "paling cepat",
        )
    )


def _wants_material_drill(question: str) -> bool:
    if _wants_monthly_time_breakdown(question):
        return False
    lowered = _normalize(question)
    return any(term in lowered for term in _DRILL_MATERIAL_TERMS)


def _time_dimension_for_metric(metric: str) -> str:
    lowered = metric.casefold()
    if "sat_oos" in lowered or ("oos" in lowered and "sat" in lowered):
        return "calmonth_date"
    if any(token in lowered for token in ("unloading", "picking", "sales_office_sell_in")):
        return "reporting_period"
    return "calmonth"


def _normalize_entity_dimension(entity_dim: str) -> str:
    if entity_dim == "material_code":
        return "material"
    if entity_dim == "sales_office":
        return "sales_off"
    return entity_dim


def _entity_supports_time_series(
    last_metric: str,
    entity_dim: str,
    last_dimensions: list[str],
) -> tuple[str, str] | None:
    """Map prior ranking metric + entity grain → governed time-series query."""
    m = last_metric.casefold()
    ed = _normalize_entity_dimension(entity_dim)
    time_dim = _time_dimension_for_metric(last_metric)
    dims = {str(d) for d in last_dimensions}

    if ed == "material":
        if "unfulfilled" in m:
            return "sales_office_service_unfulfilled_quantity", time_dim
        if "fill_rate" in m or "service" in m:
            return "sales_office_service_fill_rate", time_dim
        if "sell_out" in m or "b2b" in m:
            if "branch" in dims:
                return "b2b_branch_material_sell_out_value", time_dim
            return "material_sell_out_value", time_dim
        if "stock_tempo" in m or "warehouse" in m:
            return "material_warehouse_stock_quantity", time_dim
        if "promo" in m or "uplift" in m:
            return "promo_material_revenue_uplift", time_dim
        if "oos" in m:
            return "sat_oos_rate", "calmonth_date"
        if "sales_off" in dims or "sales_office" in dims:
            return "sales_office_material_sell_in_value", time_dim
        return "material_sell_in_value", time_dim

    if ed == "branch":
        if "material" in dims:
            return "b2b_branch_material_sell_out_value", time_dim
        return "b2b_branch_sell_out_value", time_dim

    if ed == "sales_off":
        if "unfulfilled" in m:
            return "sales_office_service_unfulfilled_quantity", time_dim
        if "fill_rate" in m or "service" in m:
            return "sales_office_service_fill_rate", time_dim
        if "unloading" in m:
            return "average_unloading_minutes", time_dim
        if "picking" in m:
            return "average_picking_minutes", time_dim
        if "sell_in" in m:
            return "sales_office_sell_in_value", time_dim
        return "sales_office_service_fill_rate", time_dim

    if ed == "dcname":
        if "store" in m or "plu" in dims:
            return "sat_store_stock_quantity", time_dim
        return "sat_dc_stock_quantity", time_dim

    if ed == "plant":
        return "stock_tempo_total_qty", time_dim

    if ed == "plu":
        return "sat_store_stock_quantity", time_dim

    if ed == "customer":
        if "sell_out" in m:
            return "material_sell_out_value", time_dim
        return "material_sell_in_value", time_dim

    if ed == "e_store":
        return "b2b_branch_sell_out_value", time_dim

    if time_dim == "calmonth":
        return last_metric, time_dim
    return None


def _referential_entity_for_time_breakdown(question: str, filter_entity: dict[str, Any]) -> bool:
    if _wants_prior_top_entity_focus(question):
        return True
    if _parse_rank_index(question) is not None:
        return True
    if filter_entity.get("rank") is not None:
        return True
    from app.services.session_context import is_referential_follow_up

    if is_referential_follow_up(question):
        return True
    eid = _normalize(str(filter_entity.get("id") or ""))
    if eid and eid.casefold() in _normalize(question):
        return True
    return False


def _append_filter_entity_predicate(
    entity: dict[str, Any],
    predicates: list[str],
    *,
    default_grain: str,
) -> None:
    ent_dim = _normalize_entity_dimension(
        str(entity.get("entity_type") or entity.get("dimension") or default_grain)
    )
    flexible = ent_dim in ("branch", "dcname")
    payload = {**entity, "entity_type": ent_dim, "dimension": ent_dim}
    pred = _entity_predicate(payload, default_grain=ent_dim, flexible_branch=flexible)
    if pred and pred not in predicates:
        predicates.append(pred)


def _plan_filtered_entity_time_breakdown(
    question: str,
    ctx: dict[str, Any],
    filter_entity: dict[str, Any],
) -> FollowUpPlan | None:
    if not filter_entity or not _wants_monthly_time_breakdown(question):
        return None
    if not _referential_entity_for_time_breakdown(question, filter_entity):
        return None
    last_metric = str(ctx.get("last_metric") or "")
    if not last_metric:
        return None
    ent_dim = _normalize_entity_dimension(
        str(
            filter_entity.get("entity_type")
            or filter_entity.get("dimension")
            or ctx.get("active_grain")
            or ""
        )
    )
    resolved = _entity_supports_time_series(
        last_metric, ent_dim, list(ctx.get("last_dimensions") or [])
    )
    if not resolved:
        return None
    metric, time_dim = resolved
    metric_override = metric if metric.casefold() != last_metric.casefold() else None
    return FollowUpPlan(
        intent="filter_entity",
        filter_entity=filter_entity,
        to_grain=None,
        limit=None,
        domain_id=str(ctx.get("domain_id")) if ctx.get("domain_id") else None,
        from_grain=str(ctx.get("active_grain") or ent_dim) or None,
        metric_override=metric_override,
        dimensions_override=[time_dim],
    )


def _wants_history_only_explanation(question: str) -> bool:
    """Explain / why questions on prior ranking without a new governed query."""
    lowered = _normalize(question)
    asks_why = any(
        t in lowered
        for t in (
            "kenapa",
            "mengapa",
            "why",
            "explain",
            "jelaskan",
            "alasan",
            "sebab",
            "what makes",
            "apa yang membuat",
        )
    )
    if not asks_why:
        return False
    vs_peers = any(
        t in lowered
        for t in (
            "dibanding yang lain",
            "dibandingkan yang lain",
            "vs yang lain",
            "versus yang lain",
            "dari yang lain",
            "daripada yang lain",
            "material lain",
            "produk lain",
            "ranking tadi",
            "hasil tadi",
            "daftar tadi",
            "top tadi",
            "dari ranking",
            "dari daftar",
            "dibanding rank",
            "dibanding urutan",
            "paling tinggi dibanding",
            "tertinggi dibanding",
            "lebih tinggi dari yang",
            "bisa paling tinggi",
            "compare to others",
            "compared to others",
            "rest of the list",
        )
    )
    rank_focus = any(
        t in lowered
        for t in (
            "urutan 1",
            "rank 1",
            "ranking 1",
            "no 1",
            "no. 1",
            "pertama",
            "paling atas",
            "teratas",
            "top 1",
        )
    )
    prior_ref = any(t in lowered for t in ("tadi", "tersebut", "di atas", "jawaban", "hasil query"))
    return vs_peers or (rank_focus and asks_why) or (prior_ref and asks_why and not _wants_material_drill(question))


def _asks_explicit_governed_compare(question: str) -> bool:
    """Compare verbs for new SQL — not Indonesian *dibanding* (vs peers explain)."""
    lowered = _normalize(question)
    if any(t in lowered for t in ("bandingkan", "compare", " vs ", "versus")):
        return True
    return bool(re.search(r"\bbanding\b", lowered))


def _follow_up_requires_fresh_query(question: str) -> bool:
    """Follow-ups that must hit Impala again (drill, cross-domain, explicit compare SQL)."""
    if _wants_history_only_explanation(question):
        return False
    lowered = _normalize(question)
    if _wants_material_drill(question):
        return True
    if _wants_monthly_time_breakdown(question):
        from app.services.session_context import is_referential_follow_up

        if (
            _wants_prior_top_entity_focus(question)
            or _parse_rank_index(question) is not None
            or is_referential_follow_up(question)
        ):
            return True
    if _wants_b2b_material_crosscheck(question):
        return True
    if _wants_sell_out_product_drill(question):
        return True
    if _wants_unfulfilled_material_drill(question):
        return True
    if _wants_branch_contribution_drill(question):
        return True
    if _wants_sell_in_crosscheck(question) and (
        any(t in lowered for t in ("cek", "compare", "samakan")) or _asks_explicit_governed_compare(question)
    ):
        return True
    if _wants_plant_breakdown(question):
        return True
    if _wants_dc_support_drill(question) or _wants_plu_drill_at_dc(question):
        return True
    if _RELIMIT_RE.search(lowered):
        return True
    if _COMPARE_PAIR_RE.search(lowered):
        return True
    if len(re.findall(r"\b(0\d{3})\b", question)) >= 2 and _asks_explicit_governed_compare(question):
        return True
    if len(_dc_cities_from_text(question)) >= 2 and _asks_explicit_governed_compare(question):
        return True
    return False


def _parse_rank_index(question: str) -> int | None:
    lowered = _normalize(question)
    match = _RANK_N_RE.search(lowered)
    if match:
        return int(match.group(1))
    if any(t in lowered for t in ("pertama", "paling atas", "teratas", "top 1", "rank 1", "urutan 1")):
        return 1
    if any(t in lowered for t in ("plant teratas", "pabrik teratas")) and "tadi" in lowered:
        return 1
    if "gap terbesar" in lowered and "tadi" in lowered:
        return 1
    if any(t in lowered for t in ("paling jelek", "terjelek", "terburuk")) and any(
        t in lowered for t in ("cabang", "office", "sales", "fill", "service")
    ):
        return 1
    if any(t in lowered for t in ("kritis", "paling kritis", "paling rendah", "terendah")) and any(
        t in lowered for t in ("material", "stok", "stock", "cover")
    ):
        return 1
    if any(t in lowered for t in ("kelima", "ke lima", "ke-5", "urutan 5")):
        return 5
    if any(t in lowered for t in ("terakhir", "paling bawah")):
        return -1
    return None


def _catalog_by_rank(catalog: list[dict[str, Any]], rank: int) -> dict[str, Any] | None:
    if not catalog:
        return None
    if rank == -1:
        return catalog[-1]
    for item in catalog:
        if item.get("rank") == rank:
            return item
    if 1 <= rank <= len(catalog):
        return catalog[rank - 1]
    return None


def _parse_compare_ranks(question: str) -> tuple[int, int] | None:
    lowered = _normalize(question)
    pair = _COMPARE_PAIR_RE.search(lowered)
    if pair:
        return int(pair.group(1)), int(pair.group(2))
    if "urutan 1" in lowered and "urutan 2" in lowered:
        return 1, 2
    return None


def _wants_plant_breakdown(question: str) -> bool:
    lowered = _normalize(question)
    return "per plant" in lowered or "by plant" in lowered or "per pabrik" in lowered


def _wants_branch_contribution_drill(question: str) -> bool:
    lowered = _normalize(question)
    return any(t in lowered for t in ("dc mana", "cabang mana", "kontribusi", "branch mana"))


def _wants_dc_support_drill(question: str) -> bool:
    lowered = _normalize(question)
    return any(t in lowered for t in ("menopang", "menyokong", "mendukung")) and "dc" in lowered


def _wants_plu_drill_at_dc(question: str) -> bool:
    lowered = _normalize(question)
    return "plu" in lowered or "stok retail" in lowered or "retail" in lowered


def _wants_sell_out_product_drill(question: str) -> bool:
    lowered = _normalize(question)
    material_ref = any(t in lowered for t in _DRILL_MATERIAL_TERMS) or any(
        t in lowered for t in ("produk/material", "material itu", "produk itu")
    )
    if any(t in lowered for t in ("sell-out", "sell out", "sellout")) and material_ref:
        return True
    return any(t in lowered for t in ("b2b", "penjualan b2b")) and material_ref


def _wants_b2b_material_crosscheck(question: str) -> bool:
    """Sell-in material context → check B2B sell-out / sameness (journey metric)."""
    lowered = _normalize(question)
    mentions_b2b = any(
        t in lowered
        for t in ("b2b", "sell-out", "sell out", "sellout", "alfamart", "partner", "penjualan b2b")
    )
    if not mentions_b2b:
        return False
    return any(
        t in lowered
        for t in (
            "sama",
            "bandingkan",
            "banding",
            "compare",
            "perbandingan",
            " vs ",
            "versus",
            "cek juga",
            "cek di",
            "apakah",
            "selaras",
            "konsisten",
        )
    ) or any(t in lowered for t in (*_DRILL_MATERIAL_TERMS, "itu", "tadi", "tersebut"))


def _wants_sell_in_crosscheck(question: str) -> bool:
    lowered = _normalize(question)
    return any(
        t in lowered
        for t in ("sell-in", "sell in", "sell in q4", "penjualan tempo", "billing", "sell-in q4")
    )


def _wants_unfulfilled_material_drill(question: str) -> bool:
    lowered = _normalize(question)
    return any(
        t in lowered
        for t in (
            "unfulfilled",
            "belum terpenuhi",
            "qty unfulfilled",
            "quantity unfulfilled",
            "selisih do",
            "do vs po",
        )
    ) and any(t in lowered for t in _DRILL_MATERIAL_TERMS)


_DC_CITY_STOP = frozenset({
    "mana", "yang", "dengan", "partner", "alfamart", "tertinggi", "terbesar", "terbanyak",
    "stok", "stock", "sat", "di", "ke", "dan", "atau", "untuk", "pada",
})


def _dc_cities_from_text(text: str) -> list[str]:
    cities: list[str] = []
    for match in re.finditer(r"\bdc\s+([A-Za-z]+)", text, re.IGNORECASE):
        city = match.group(1)
        if city.casefold() in _DC_CITY_STOP:
            continue
        label = city.title()
        if label not in cities:
            cities.append(label)
    return cities


def _bind_entity_from_catalog(question: str, catalog: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not catalog:
        return None
    lowered = _normalize(question)
    rank = _parse_rank_index(question)
    if rank is not None:
        bound = _catalog_by_rank(catalog, rank)
        if bound:
            return bound
    # Rank references (legacy phrases)
    if any(
        t in lowered
        for t in (
            "muncul di jawaban",
            "di jawaban tadi",
            "yang muncul",
            "dari jawaban",
            "dc yang",
            "status dominan",
            "dominan tadi",
        )
    ):
        return catalog[0]
    if any(t in lowered for t in ("terburuk", "paling buruk", "outlet terburuk", "toko terburuk")):
        return catalog[0]
    if any(
        t in lowered
        for t in (
            "material itu",
            "produk itu",
            "produk/material itu",
            "produk/material",
            "material tersebut",
            "produk tersebut",
            "sku itu",
            "office itu",
            "cabang itu",
            "dc itu",
            "sales office itu",
            "partner itu",
        )
    ):
        return catalog[0]
    if any(
        t in lowered
        for t in (
            "pertama",
            "paling atas",
            "paling tinggi",
            "tertinggi",
            "terbesar",
            "teratas",
            "rank 1",
            "urutan 1",
            "top 1",
        )
    ):
        for item in catalog:
            if item.get("rank") == 1:
                return item
        return catalog[0]
    if any(t in lowered for t in ("terakhir", "paling bawah")):
        return catalog[-1]
    # Substring match on entity id (e.g. palembang → DC Palembang)
    for item in catalog:
        eid = _normalize(str(item.get("id") or ""))
        if not eid:
            continue
        tokens = [t for t in re.split(r"[\s_/\-]+", eid) if len(t) >= 4]
        for token in tokens:
            if token in lowered:
                return item
        if eid in lowered or lowered in eid:
            return item
    # "cabang X" / "branch X" single token
    match = re.search(
        r"\b(?:cabang|branch|dc)\s+([^,]+?)(?:\s*,|\s+top\b|\s+based\b|\s+produk\b|\s+product\b|$)",
        lowered,
        re.IGNORECASE,
    )
    if match:
        phrase = match.group(1).strip()
        for item in catalog:
            if phrase in _normalize(str(item.get("id") or "")):
                return item
        for token in re.split(r"[\s_/\-]+", phrase):
            if len(token) < 4:
                continue
            for item in catalog:
                if token in _normalize(str(item.get("id") or "")):
                    return item
    return None


@dataclass
class FollowUpPlan:
    intent: str
    filter_entity: dict[str, Any] | None
    to_grain: str | None
    limit: int | None
    domain_id: str | None
    from_grain: str | None
    compare_entities: list[dict[str, Any]] | None = None
    filter_entities: list[dict[str, Any]] | None = None
    breakdown_dimension: str | None = None
    metric_override: str | None = None
    dimensions_override: list[str] | None = None
    extra_predicates: list[str] | None = None


def _resolve_follow_up_plan(
    question: str,
    ctx: dict[str, Any],
    understanding: "TurnUnderstanding | None",
) -> FollowUpPlan | None:
    if not ctx.get("last_metric"):
        return None
    from app.services.session_context import is_referential_follow_up

    plan = plan_follow_up(question, ctx)
    if plan:
        return plan
    referential = is_referential_follow_up(question) or bool(
        understanding and understanding.referential_follow_up
    )
    if not referential:
        return None
    if understanding and understanding.referential_follow_up:
        return plan_from_understanding(understanding, ctx)
    return None


def plan_from_understanding(u: "TurnUnderstanding", ctx: dict[str, Any]) -> FollowUpPlan | None:
    if not u.referential_follow_up or not ctx.get("last_metric"):
        return None
    catalog = list(ctx.get("result_catalog") or [])
    filter_entity: dict[str, Any] | None = None
    if u.follow_up_entity_id:
        eid = u.follow_up_entity_id.strip()
        for item in catalog:
            sid = str(item.get("id") or "").strip()
            if sid == eid or eid.casefold() in sid.casefold():
                filter_entity = item
                break
        if filter_entity is None:
            dim = u.follow_up_entity_dimension or ctx.get("active_grain") or "branch"
            filter_entity = {
                "id": eid,
                "entity_type": dim,
                "dimension": dim,
                "rank": u.follow_up_rank,
            }
    elif u.follow_up_rank and catalog:
        for item in catalog:
            if item.get("rank") == u.follow_up_rank:
                filter_entity = item
                break
        if filter_entity is None and 1 <= int(u.follow_up_rank) <= len(catalog):
            filter_entity = catalog[int(u.follow_up_rank) - 1]

    question = (u.pipeline_question or "").strip()
    if filter_entity:
        time_plan = _plan_filtered_entity_time_breakdown(question, ctx, filter_entity)
        if time_plan:
            return time_plan

    to_grain: str | None = "material" if u.follow_up_material_drill else None
    limit: int | None = u.follow_up_top_n if u.follow_up_material_drill else None
    if u.follow_up_material_drill and not limit:
        limit = 5
    intent = "drill_down" if to_grain else "continue"
    if filter_entity and not to_grain:
        intent = "filter_entity"
    if not filter_entity and not to_grain:
        return None
    return FollowUpPlan(
        intent=intent,
        filter_entity=filter_entity,
        to_grain=to_grain,
        limit=limit,
        domain_id=str(ctx.get("domain_id")) if ctx.get("domain_id") else None,
        from_grain=str(ctx.get("active_grain") or ctx.get("entity_dimension") or "") or None,
    )


def _question_wants_office_sell_in_compare(question: str) -> bool:
    lowered = _normalize(question)
    if any(
        t in lowered
        for t in (
            "sell-in",
            "sell in",
            "sellin",
            "penjualan",
            "billing",
            "total sell",
            "gross billing",
        )
    ):
        return True
    return "total" in lowered and any(t in lowered for t in ("office", "sales office", "kantor", "cabang"))


def _is_explicit_new_ranking_question(question: str) -> bool:
    """Fresh top-N ranking (not a drill on prior entity), e.g. after a pareto turn."""
    lowered = _normalize(question)
    if not _TOP_N_RE.search(lowered):
        return False
    if any(
        t in lowered
        for t in (
            "tadi",
            "sebelumnya",
            "pertanyaan tadi",
            "dari hasil",
            "paling jelek",
            "terjelek",
            "terburuk",
            "rank 1",
            "urutan 1",
        )
    ):
        return False
    if not any(t in lowered for t in ("material", "produk", "sku", "plu", "office", "cabang", "dc")):
        return False
    return any(
        t in lowered
        for t in (
            "sell-in",
            "sell in",
            "sell-out",
            "sell out",
            "tertinggi",
            "terbesar",
            "terendah",
            "terkecil",
            "fill rate",
            "stok",
            "stock",
        )
    )


def plan_follow_up(question: str, ctx: dict[str, Any]) -> FollowUpPlan | None:
    if not ctx.get("last_metric"):
        return None
    if _is_explicit_new_ranking_question(question):
        return None
    catalog = list(ctx.get("result_catalog") or [])
    domain_id = ctx.get("domain_id")
    from_grain = ctx.get("active_grain") or ctx.get("entity_dimension")
    lowered = _normalize(question)
    last_metric = str(ctx.get("last_metric") or "")

    office_codes = re.findall(r"\b(0\d{3})\b", f"{ctx.get('last_question') or ''} {question}")
    office_codes = list(dict.fromkeys(office_codes))
    if len(office_codes) >= 2 and any(
        t in lowered
        for t in (
            "lebih lambat",
            "selisih",
            "mana yang lebih",
            "perbedaan",
            "bandingkan",
            "banding",
            "compare",
            " vs ",
            "versus",
        )
    ):
        ents: list[dict[str, Any]] = []
        for idx, code in enumerate(office_codes[:2]):
            ents.append(
                {
                    "rank": idx + 1,
                    "id": code,
                    "entity_type": "sales_office",
                    "dimension": "sales_office",
                }
            )
        metric_override = (
            "sales_office_sell_in_value"
            if _question_wants_office_sell_in_compare(question)
            else None
        )
        return FollowUpPlan(
            intent="compare",
            filter_entity=None,
            to_grain=None,
            limit=None,
            domain_id=str(domain_id) if domain_id else None,
            from_grain="sales_office",
            compare_entities=ents,
            metric_override=metric_override,
        )

    single_office = re.findall(r"\b(0\d{3})\b", question)
    if (
        len(single_office) == 1
        and catalog
        and any(
            t in lowered
            for t in ("bandingkan", "banding", "compare", " vs ", "versus")
        )
        and any(
            t in lowered
            for t in (
                "tercepat",
                "paling cepat",
                "office tercepat",
                "cabang tercepat",
                "terlama",
                "paling lambat",
            )
        )
    ):
        anchor = _catalog_by_rank(catalog, 1)
        if anchor:
            grain = str(anchor.get("dimension") or anchor.get("entity_type") or "sales_office")
            code = single_office[0]
            compare_ents = [
                anchor,
                {
                    "rank": 2,
                    "id": code,
                    "entity_type": grain,
                    "dimension": grain,
                },
            ]
            return FollowUpPlan(
                intent="compare",
                filter_entity=None,
                to_grain=None,
                limit=None,
                domain_id=str(domain_id) if domain_id else None,
                from_grain=grain,
                compare_entities=compare_ents,
            )

    combined_text = f"{ctx.get('last_question') or ''} {question}"
    dc_cities = _dc_cities_from_text(combined_text)
    if len(dc_cities) >= 2 and any(
        t in lowered
        for t in (
            "bandingkan",
            "banding",
            "compare",
            " vs ",
            "versus",
            "dengan",
        )
    ):
        if domain_id == "stock_sat" or "sat_dc" in last_metric.casefold():
            compare_ents = [
                {
                    "rank": idx + 1,
                    "id": city,
                    "entity_type": "dcname",
                    "dimension": "dcname",
                }
                for idx, city in enumerate(dc_cities[:2])
            ]
            return FollowUpPlan(
                intent="compare",
                filter_entity=None,
                to_grain=None,
                limit=None,
                domain_id="stock_sat",
                from_grain="dcname",
                compare_entities=compare_ents,
            )

    last_dims = list(ctx.get("last_dimensions") or [])
    promo_context = (
        domain_id == "promo"
        or "promo_observation" in last_metric.casefold()
        or "program_status" in last_dims
    )
    if promo_context and any(t in lowered for t in ("uplift", "by uplift")) and any(
        t in lowered for t in ("status dominan", "dominan tadi", "tadi", "dominan")
    ):
        ent = _bind_entity_from_catalog(question, catalog) or (catalog[0] if catalog else None)
        if ent is None and "program_status" in last_dims:
            ent = {
                "rank": 1,
                "id": "Y",
                "entity_type": "program_status",
                "dimension": "program_status",
            }
        return FollowUpPlan(
            intent="drill_down",
            filter_entity=ent,
            to_grain="material",
            limit=_parse_top_n(question, default=5),
            domain_id="promo",
            from_grain=str(from_grain or "program_status"),
            metric_override="promo_material_revenue_uplift",
        )

    if (
        domain_id == "service_level"
        or "fill_rate" in last_metric.casefold()
        or "fill_rate_band" in last_dims
    ) and any(
        t in lowered
        for t in ("band terendah", "band paling rendah", "lowest band", "low fill", "low_fill")
    ) or (
        "terendah" in lowered
        and "band" in lowered
        and any(t in lowered for t in ("sales office", "office", "cabang", "dominan", "list"))
    ):
        return FollowUpPlan(
            intent="drill_down",
            filter_entity={
                "id": "low_fill",
                "entity_type": "fill_rate_band",
                "dimension": "fill_rate_band",
                "rank": None,
            },
            to_grain="sales_off",
            limit=10,
            domain_id="service_level",
            from_grain="fill_rate_band",
            metric_override="sales_office_service_fill_rate",
        )

    mat_match = _MATERIAL_CODE_RE.search(question)
    if mat_match:
        code = mat_match.group(1).upper()
        filter_entity = {
            "id": code,
            "entity_type": "material",
            "dimension": "material",
            "rank": None,
        }
        metric_override = None
        if _wants_sell_in_crosscheck(question):
            metric_override = "material_sell_in_value"
        elif domain_id == "stock_tempo" or "stock" in last_metric.casefold() or "warehouse" in last_metric.casefold():
            metric_override = "material_warehouse_stock_quantity"
        return FollowUpPlan(
            intent="filter_entity",
            filter_entity=filter_entity,
            to_grain=None,
            limit=None,
            domain_id=str(domain_id) if domain_id else None,
            from_grain=str(from_grain) if from_grain else None,
            metric_override=metric_override,
        )

    if catalog and any(t in lowered for t in ("kontribusi", "persen kontribusi", "percent contribution")):
        if any(t in lowered for t in ("tiga produk", "3 produk", "top 3", "top3", "teratas tadi", "produk teratas")):
            return FollowUpPlan(
                intent="relimit",
                filter_entity=None,
                to_grain=None,
                limit=3,
                domain_id=str(domain_id) if domain_id else None,
                from_grain=str(from_grain) if from_grain else None,
            )

    if (
        catalog
        and len(catalog) >= 2
        and any(t in lowered for t in ("tercepat", "paling cepat", "efisien"))
        and any(t in lowered for t in ("terlama", "terlambat", "paling lambat", "tertinggi"))
        and any(t in lowered for t in ("ranking", "daftar", "sama", "bandingkan", " vs "))
    ):
        slow_ent = catalog[0]
        fast_ent = catalog[-1]
        grain = str(slow_ent.get("dimension") or slow_ent.get("entity_type") or "sales_office")
        return FollowUpPlan(
            intent="compare",
            filter_entity=None,
            to_grain=None,
            limit=None,
            domain_id=str(domain_id) if domain_id else None,
            from_grain=grain,
            compare_entities=[slow_ent, fast_ent],
        )

    relimit = _RELIMIT_RE.search(lowered)
    if relimit:
        return FollowUpPlan(
            intent="relimit",
            filter_entity=None,
            to_grain=None,
            limit=int(relimit.group(1)),
            domain_id=str(domain_id) if domain_id else None,
            from_grain=str(from_grain) if from_grain else None,
        )

    compare = _parse_compare_ranks(question)
    if compare and len(catalog) >= 2:
        a, b = compare
        ents = [_catalog_by_rank(catalog, a), _catalog_by_rank(catalog, b)]
        if ents[0] and ents[1]:
            return FollowUpPlan(
                intent="compare",
                filter_entity=None,
                to_grain=None,
                limit=None,
                domain_id=str(domain_id) if domain_id else None,
                from_grain=str(from_grain) if from_grain else None,
                compare_entities=[ents[0], ents[1]],
            )

    if _wants_plant_breakdown(question) and catalog:
        n = 3 if re.search(r"\btop\s*3\b", lowered) else 3
        subset = catalog[:n]
        return FollowUpPlan(
            intent="plant_breakdown",
            filter_entity=None,
            to_grain="plant",
            limit=None,
            domain_id=str(domain_id) if domain_id else None,
            from_grain=str(from_grain) if from_grain else None,
            filter_entities=subset,
            breakdown_dimension="plant",
        )

    if catalog and _wants_history_only_explanation(question) and not _follow_up_requires_fresh_query(question):
        rank = _parse_rank_index(question)
        focus = _catalog_by_rank(catalog, rank) if rank is not None else None
        return FollowUpPlan(
            intent="explain_prior_result",
            filter_entity=focus,
            to_grain=None,
            limit=None,
            domain_id=str(domain_id) if domain_id else None,
            from_grain=str(from_grain) if from_grain else None,
        )

    filter_entity = _bind_entity_from_catalog(question, catalog)
    if (
        not filter_entity
        and catalog
        and _wants_prior_top_entity_focus(question)
        and any(t in lowered for t in ("paling tinggi", "tertinggi", "terbesar", "terbanyak"))
    ):
        filter_entity = _catalog_by_rank(catalog, 1)

    if filter_entity:
        time_breakdown = _plan_filtered_entity_time_breakdown(question, ctx, filter_entity)
        if time_breakdown:
            return time_breakdown

    from app.services.cross_domain_compare import try_resolve_cross_domain

    cross = try_resolve_cross_domain(
        question,
        filter_entity=filter_entity,
        from_grain=str(from_grain) if from_grain else None,
        allow_implicit_b2b_check=True,
    )
    if cross and filter_entity:
        return FollowUpPlan(
            intent="filter_entity",
            filter_entity=filter_entity,
            to_grain=None,
            limit=None,
            domain_id="cross_domain",
            from_grain=str(from_grain or filter_entity.get("dimension") or "material"),
            metric_override=cross.metric,
            dimensions_override=list(cross.dimensions),
            extra_predicates=list(cross.follow_up_entity_filters),
        )

    if filter_entity and from_grain == "division" and (
        _wants_dc_support_drill(question) or _wants_branch_contribution_drill(question)
    ):
        return FollowUpPlan(
            intent="drill_down",
            filter_entity=filter_entity,
            to_grain="dcname",
            limit=_parse_top_n(question, default=10),
            domain_id="stock_sat",
            from_grain="division",
            metric_override="sat_dc_stock_quantity",
        )

    if (
        filter_entity
        and str(filter_entity.get("dimension") or filter_entity.get("entity_type") or "") == "dcname"
        and _wants_plu_drill_at_dc(question)
    ):
        return FollowUpPlan(
            intent="drill_down",
            filter_entity=filter_entity,
            to_grain="plu",
            limit=_parse_top_n(question, default=5),
            domain_id="stock_sat",
            from_grain="dcname",
            metric_override="sat_store_stock_quantity",
        )

    if (
        filter_entity
        and _wants_unfulfilled_material_drill(question)
        and (
            domain_id == "service_level"
            or "fill_rate" in last_metric.casefold()
            or "service" in last_metric.casefold()
        )
    ):
        grain = str(filter_entity.get("dimension") or filter_entity.get("entity_type") or "sales_off")
        return FollowUpPlan(
            intent="drill_down",
            filter_entity=filter_entity,
            to_grain="material",
            limit=_parse_top_n(question, default=5),
            domain_id="service_level",
            from_grain=grain,
            metric_override="sales_office_service_unfulfilled_quantity",
        )

    if filter_entity and _wants_sell_out_product_drill(question):
        grain = str(filter_entity.get("dimension") or filter_entity.get("entity_type") or "branch")
        if grain in ("dcname", "branch"):
            limit = _parse_top_n(question, default=3)
            return FollowUpPlan(
                intent="drill_down",
                filter_entity=filter_entity,
                to_grain="material",
                limit=limit,
                domain_id="b2b",
                from_grain=grain,
                metric_override="b2b_branch_material_sell_out_value",
            )

    if filter_entity and domain_id == "promo" and any(
        t in lowered for t in ("status dominan", "dominan tadi", "by uplift", "uplift", "material")
    ):
        return FollowUpPlan(
            intent="drill_down",
            filter_entity=filter_entity,
            to_grain="material",
            limit=_parse_top_n(question, default=5),
            domain_id="promo",
            from_grain=str(from_grain or "program_status"),
            metric_override="promo_material_revenue_uplift",
        )

    if (
        not filter_entity
        and catalog
        and domain_id == "promo"
        and any(t in lowered for t in ("status dominan", "dominan tadi"))
    ):
        filter_entity = catalog[0]
        return FollowUpPlan(
            intent="drill_down",
            filter_entity=filter_entity,
            to_grain="material",
            limit=_parse_top_n(question, default=5),
            domain_id="promo",
            from_grain=str(from_grain or "program_status"),
            metric_override="promo_material_revenue_uplift",
        )

    if (
        not filter_entity
        and catalog
        and any(t in lowered for t in ("lebih lambat", "paling lambat", "terlambat"))
        and any(t in last_metric.casefold() for t in ("unloading", "picking"))
    ):
        filter_entity = catalog[-1]
    to_grain: str | None = None
    limit: int | None = None
    intent = "continue"
    metric_override: str | None = None

    if filter_entity and _wants_branch_contribution_drill(question) and from_grain in ("material", "material_code"):
        return FollowUpPlan(
            intent="drill_down",
            filter_entity=filter_entity,
            to_grain="branch",
            limit=10,
            domain_id=str(domain_id) if domain_id else None,
            from_grain=str(from_grain) if from_grain else None,
            metric_override="b2b_branch_sell_out_value",
        )

    if filter_entity and _wants_sell_in_crosscheck(question) and domain_id == "stock_tempo":
        return FollowUpPlan(
            intent="filter_entity",
            filter_entity=filter_entity,
            to_grain=None,
            limit=None,
            domain_id=str(domain_id) if domain_id else None,
            from_grain=str(from_grain) if from_grain else None,
            metric_override="material_sell_in_value",
        )

    if any(
        t in lowered
        for t in (
            "company-wide",
            "company wide",
            "seluruh perusahaan",
            "companywide",
            "nasional",
            "seluruh tempo",
        )
    ) or (
        "rata-rata" in lowered
        and any(t in lowered for t in ("company", "seluruh", "nasional", "perusahaan"))
        and ("unloading" in last_metric.casefold() or "picking" in last_metric.casefold())
    ):
        if "unloading" in last_metric.casefold() or "picking" in last_metric.casefold():
            return FollowUpPlan(
                intent="aggregate",
                filter_entity=None,
                to_grain=None,
                limit=None,
                domain_id=str(domain_id) if domain_id else None,
                from_grain=str(from_grain) if from_grain else None,
            )

    if _wants_material_drill(question):
        to_grain = "material"
        limit = _parse_top_n(question, default=3 if "3" in question else 5)
        intent = "drill_down"

    if filter_entity and not to_grain:
        intent = "filter_entity"

    if filter_entity and _wants_sell_in_crosscheck(question):
        metric_override = "material_sell_in_value"

    if not filter_entity and not to_grain:
        return None
    return FollowUpPlan(
        intent=intent,
        filter_entity=filter_entity,
        to_grain=to_grain,
        limit=limit,
        domain_id=str(domain_id) if domain_id else None,
        from_grain=str(from_grain) if from_grain else None,
        metric_override=metric_override,
    )


def _entity_predicate(entity: dict[str, Any], *, default_grain: str, flexible_branch: bool = False) -> str | None:
    dim = str(entity.get("entity_type") or entity.get("dimension") or default_grain)
    eid = str(entity.get("id") or "")
    if not eid:
        return None
    lit = _sql_string_literal(eid)
    if flexible_branch and dim == "branch":
        # Partner DC labels vary slightly between result table and Impala (e.g. "DC Palembang").
        return f"(d.branch = {lit} OR UPPER(d.branch) LIKE CONCAT('%', UPPER({lit}), '%'))"
    if flexible_branch and dim == "dcname":
        city = re.sub(r"^dc\s+", "", eid, flags=re.IGNORECASE).strip()
        city_lit = _sql_string_literal(city)
        return f"UPPER(d.dcname) LIKE CONCAT('%', UPPER({city_lit}), '%')"
    return f"d.{dim} = {lit}"


def _entities_in_predicate(
    entities: list[dict[str, Any]], *, default_grain: str, flexible_dcname: bool = False
) -> str | None:
    dim = default_grain
    ids: list[str] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        dim = str(ent.get("entity_type") or ent.get("dimension") or dim)
        eid = str(ent.get("id") or "")
        if eid:
            ids.append(eid)
    if not ids:
        return None
    if flexible_dcname and dim == "dcname":
        parts = []
        for eid in ids:
            pred = _entity_predicate(
                {"id": eid, "entity_type": "dcname", "dimension": "dcname"},
                default_grain=dim,
                flexible_branch=True,
            )
            if pred:
                parts.append(pred)
        if parts:
            return f"({' OR '.join(parts)})"
    quoted = [_sql_string_literal(eid) for eid in ids]
    if len(quoted) == 1:
        return f"d.{dim} = {quoted[0]}"
    return f"d.{dim} IN ({', '.join(quoted)})"


def _drill_metric_and_dimensions(plan: FollowUpPlan, ctx: dict[str, Any]) -> tuple[str, list[str], list[str]] | None:
    """Return (metric, dimensions, extra_sql_predicates) for governed compile."""
    domain = plan.domain_id or ctx.get("domain_id")
    last_metric = str(plan.metric_override or ctx.get("last_metric") or "")
    default_grain = str(plan.from_grain or ctx.get("active_grain") or "branch")
    predicates: list[str] = []
    entity = plan.filter_entity

    if plan.intent == "relimit":
        dims = list(ctx.get("last_dimensions") or [])
        if not dims and default_grain:
            dims = [default_grain]
        return str(ctx.get("last_metric") or last_metric), dims, []

    if plan.intent == "aggregate":
        return last_metric, [], []

    if plan.intent == "compare" and plan.compare_entities:
        grain = str(plan.compare_entities[0].get("dimension") or default_grain or "sales_office")
        pred = _entities_in_predicate(
            plan.compare_entities,
            default_grain=grain,
            flexible_dcname=(grain == "dcname"),
        )
        if pred:
            predicates.append(pred)
        if plan.metric_override:
            dims = ["sales_office"] if grain in ("sales_office", "sales_off") else [grain]
            return plan.metric_override, dims, predicates
        if grain == "dcname":
            return "sat_dc_stock_quantity", ["dcname"], predicates
        ctx_metric = str(ctx.get("last_metric") or "").casefold()
        if grain == "sales_office" and "unloading" in ctx_metric:
            return "average_unloading_minutes", [grain], predicates
        if grain == "sales_office" and "picking" in ctx_metric:
            return "average_picking_minutes", [grain], predicates
        if grain in ("sales_office", "sales_off") and any(
            term in ctx_metric for term in ("sell_in", "billing", "material_sell_in")
        ):
            return "sales_office_sell_in_value", [grain], predicates
        dims = list(ctx.get("last_dimensions") or [grain])
        return str(ctx.get("last_metric") or last_metric), dims, predicates

    if plan.intent == "plant_breakdown" and plan.filter_entities:
        grain = str(plan.filter_entities[0].get("dimension") or "material")
        pred = _entities_in_predicate(plan.filter_entities, default_grain=grain)
        if pred:
            predicates.append(pred)
        if domain == "stock_tempo" or "stock_tempo" in last_metric.casefold():
            return "stock_tempo_total_qty", ["plant", "material"], predicates
        return last_metric, ["plant", grain], predicates

    if entity:
        pred = _entity_predicate(entity, default_grain=default_grain, flexible_branch=True)
        if pred:
            predicates.append(pred)

    if plan.to_grain == "branch" and entity:
        return "b2b_branch_sell_out_value", ["branch"], predicates

    if plan.to_grain == "plu" and entity:
        preds = list(predicates)
        pred = _entity_predicate(entity, default_grain="dcname", flexible_branch=True)
        if pred:
            preds.append(pred)
        return "sat_store_stock_quantity", ["plu"], preds

    if plan.to_grain == "dcname" and entity:
        dim = str(entity.get("entity_type") or entity.get("dimension") or "division")
        preds = list(predicates)
        if dim == "division" and "division" not in " ".join(preds).casefold():
            div_lit = _sql_string_literal(str(entity.get("id") or ""))
            preds.append(f"d.division = {div_lit}")
        return "sat_dc_stock_quantity", ["dcname"], preds

    if plan.to_grain == "plant" and entity:
        if domain == "stock_tempo" or "stock" in last_metric.casefold():
            return "stock_tempo_total_qty", ["plant"], predicates

    if plan.to_grain == "sales_off":
        band_entity = entity or plan.filter_entity
        preds = list(predicates)
        if band_entity and str(band_entity.get("dimension") or "") == "fill_rate_band":
            band_id = str(band_entity.get("id") or "low_fill")
            preds.append(f"d.fill_rate_band = {_sql_string_literal(band_id)}")
        return "sales_office_service_fill_rate", ["sales_off"], preds

    if plan.to_grain == "material":
        override = str(plan.metric_override or "").casefold()
        unfulfilled_metric = "unfulfilled" in last_metric.casefold() or "unfulfilled" in override
        if unfulfilled_metric:
            dims = ["material"]
            preds = list(predicates)
            if entity and str(entity.get("entity_type") or entity.get("dimension") or "") in (
                "sales_off",
                "sales_office",
            ):
                off = str(entity.get("id") or "")
                if off:
                    dim_col = str(entity.get("dimension") or entity.get("entity_type") or "sales_off")
                    col = "sales_off" if dim_col in ("sales_off", "sales_office") else dim_col
                    if col == "sales_office":
                        col = "sales_off"
                    preds.append(f"d.{col} = {_sql_string_literal(off)}")
            return "sales_office_service_unfulfilled_quantity", dims, preds
        if domain == "stock_tempo" or "stock_tempo" in last_metric.casefold() or "warehouse" in last_metric.casefold():
            ent_type = str((entity or {}).get("entity_type") or (entity or {}).get("dimension") or "")
            if ent_type == "plant" or default_grain == "plant":
                return "stock_tempo_total_qty", ["material"], predicates
        if domain == "service_level" or "service" in last_metric.casefold() or "fill_rate" in last_metric.casefold():
            off_dim = "sales_off"
            if entity:
                ed = str(entity.get("entity_type") or entity.get("dimension") or "")
                if ed in ("sales_off", "sales_office"):
                    off_dim = ed
            dims = ["material"]
            preds = list(predicates)
            if entity and preds:
                if off_dim == "sales_office":
                    preds = [p.replace("d.sales_office", "d.sales_off") for p in preds]
                    off_dim = "sales_off"
                dims.append(off_dim)
            return "sales_office_service_fill_rate", dims, preds
        if domain == "promo" or "promo" in last_metric.casefold():
            override = str(plan.metric_override or "")
            if override == "promo_material_revenue_uplift" or "uplift" in override:
                preds = [p for p in predicates if "program_status" not in p.casefold()]
                if entity and str(entity.get("entity_type") or entity.get("dimension") or "") == "program_status":
                    status_id = str(entity.get("id") or "Y")
                    status_lit = _sql_string_literal(status_id)
                    preds.append(
                        "d.material IN (SELECT DISTINCT p.material_code "
                        "FROM gold.rpt_sat_promo_material_december_semantic p "
                        f"WHERE p.program_status = {status_lit})"
                    )
                return "promo_material_revenue_uplift", ["material"], preds
        if domain == "sales" or "sell_in" in last_metric.casefold():
            dims = ["material"]
            if entity and str(entity.get("entity_type") or "") in ("sales_office", "sales_off"):
                dims.append(str(entity["entity_type"]))
            return "sales_office_material_sell_in_value", dims, predicates
        if domain == "b2b" or "b2b" in last_metric.casefold() or "sell_out" in last_metric.casefold():
            # corr_b2b_material_plu is not reliably queryable in PoC Impala; use governed
            # material sell-out semantic (same family as management "top produk" questions).
            branch_predicates = [p for p in predicates if "dcname" not in p.casefold()]
            if entity:
                ent_dim = str(entity.get("entity_type") or entity.get("dimension") or "")
                eid = str(entity.get("id") or "")
                if ent_dim == "dcname" and eid:
                    city = re.sub(r"^dc\s+", "", eid, flags=re.IGNORECASE).strip() or eid
                    branch_predicates.append(
                        f"UPPER(d.branch) LIKE CONCAT('%', UPPER({_sql_string_literal(city)}), '%')"
                    )
                elif ent_dim == "branch" and eid:
                    branch_predicates.append(
                        _entity_predicate(entity, default_grain="branch", flexible_branch=True) or ""
                    )
                    branch_predicates = [p for p in branch_predicates if p]
            has_branch_filter = any(
                "d.branch" in p.casefold() or "upper(d.branch)" in p.casefold()
                for p in branch_predicates
            )
            if has_branch_filter:
                return "b2b_branch_material_sell_out_value", ["material"], branch_predicates
            return "material_sell_out_value", ["material"], branch_predicates
        if domain == "stock_sat":
            ent_type = str((entity or {}).get("entity_type") or (entity or {}).get("dimension") or "")
            if ent_type == "dcname" or default_grain == "dcname":
                return "sat_store_stock_quantity", ["plu"], predicates
            return "sat_store_stock_quantity", ["plu"], predicates
        if domain == "sat_oos":
            ent_type = str((entity or {}).get("entity_type") or (entity or {}).get("dimension") or "")
            if ent_type in ("cust_id", "cust_code", "customer"):
                return "sat_oos_rate", ["material_code"], predicates
            return "sat_oos_rate", ["material_code"], predicates
        return "material_sell_in_value", ["material"], predicates

    if plan.intent == "filter_entity" and entity:
        ent_dim = str(entity.get("entity_type") or entity.get("dimension") or default_grain)
        dims = list(ctx.get("last_dimensions") or [ent_dim])
        if ent_dim not in dims and len(dims) == 1 and dims[0] != ent_dim:
            dims = [ent_dim]
        metric = str(plan.metric_override or last_metric or ctx.get("last_metric") or "")
        if plan.dimensions_override is not None:
            _append_filter_entity_predicate(entity, predicates, default_grain=default_grain)
            if plan.extra_predicates:
                predicates.extend(plan.extra_predicates)
            return metric, list(plan.dimensions_override), predicates
        if metric == "material_sell_out_to_sell_in_value_ratio" and ent_dim == "material":
            pred = _entity_predicate(entity, default_grain="material")
            if pred:
                predicates.append(pred)
            return metric, ["material"], predicates
        if ent_dim in ("material", "material_code"):
            pred = _entity_predicate(entity, default_grain="material")
            if pred:
                predicates.append(pred)
        return metric, dims, predicates

    return None


def build_follow_up_rewrite(question: str, ctx: dict[str, Any], plan: FollowUpPlan) -> str:
    parts = [
        f"Q4 2024 analytic follow-up on prior question: {ctx.get('last_question', '')[:160]}.",
        f"Prior governed metric: {ctx.get('last_metric')}; domain: {ctx.get('domain_id')}; grain: {ctx.get('active_grain')}.",
    ]
    if plan.filter_entity:
        ent = plan.filter_entity
        parts.append(
            f'Filter {ent.get("entity_type")} = "{ent.get("id")}" (rank {ent.get("rank")} from prior result table).'
        )
    if (
        plan.dimensions_override
        and len(plan.dimensions_override) == 1
        and plan.filter_entity
        and plan.dimensions_override[0] in ("calmonth", "calmonth_date", "reporting_period")
    ):
        ent = plan.filter_entity
        time_dim = plan.dimensions_override[0]
        parts.append(
            f"Time series grouped by {time_dim} for {ent.get('entity_type')} "
            f'"{ent.get("id")}" only — not a new top-N ranking at the prior grain.'
        )
    if plan.to_grain == "material" and plan.limit:
        parts.append(
            f"Show top {plan.limit} materials/products by sales value consistent with prior measure family, grouped by material."
        )
    cabang = classify_cabang_grain(question, session_last_metric=str(ctx.get("last_metric") or ""))
    if cabang == "branch":
        parts.append("Interpret cabang as B2B partner branch (sell-out), not Tempo sales office sell-in.")
    elif cabang == "sales_office":
        parts.append("Interpret cabang as Tempo sales office (sell-in).")
    parts.append(f"Original user question: {question.strip()}")
    return " ".join(parts)


def _last_success_turn_with_rows(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in reversed(history):
        if str(entry.get("status") or "") != "SUCCESS":
            continue
        prior = _prior_turn_query_result(entry)
        if prior and prior.get("rows"):
            return entry
    return None


def _prior_turn_query_result(anchor: dict[str, Any]) -> dict[str, Any] | None:
    rows_raw = anchor.get("rows")
    if isinstance(rows_raw, list):
        data_rows = [row for row in rows_raw if isinstance(row, dict)]
        if data_rows:
            columns = list(data_rows[0].keys())
            return {
                "columns": columns,
                "rows": data_rows,
                "row_count": len(data_rows),
                "execution_ms": 0,
            }
    follow_rows = _rows_for_chart_follow_up(anchor)
    if not follow_rows:
        return None
    columns: list[str] = []
    for row in follow_rows:
        for key in row:
            if key not in columns:
                columns.append(str(key))
    return {
        "columns": columns,
        "rows": follow_rows,
        "row_count": len(follow_rows),
        "execution_ms": 0,
    }


def try_history_only_analysis_resolution(
    question: str,
    analysis_context: dict[str, Any],
    history: list[dict[str, Any]],
    understanding: "TurnUnderstanding | None" = None,
) -> dict[str, Any] | None:
    if not analysis_context or not history:
        return None
    if not analysis_context.get("last_metric"):
        return None
    plan = _resolve_follow_up_plan(question, analysis_context, understanding)
    if not plan or plan.intent != "explain_prior_result":
        return None
    anchor = (
        _last_governed_chart_turn(history)
        or _last_governed_success_turn(history)
        or _last_success_turn_with_rows(history)
    )
    if not anchor:
        return None
    prior_result = _prior_turn_query_result(anchor)
    if not prior_result or not prior_result.get("rows"):
        return None
    answer = anchor.get("answer") if isinstance(anchor.get("answer"), dict) else {}
    stored = anchor.get("session_frame") if isinstance(anchor.get("session_frame"), dict) else {}
    data_ref = ""
    if isinstance(answer.get("data_reference"), str):
        data_ref = answer["data_reference"].strip()
    focus = plan.filter_entity
    return {
        "status": "history_only",
        "metric": analysis_context.get("last_metric"),
        "matched_alias": "follow_up_history_only",
        "dimensions": list(analysis_context.get("last_dimensions") or []),
        "prior_query_result": prior_result,
        "prior_turn": {
            "question": str(anchor.get("question") or analysis_context.get("last_question") or ""),
            "direct_answer": str(answer.get("direct_answer") or "")[:800],
            "data_reference": data_ref,
            "strategy": str(anchor.get("strategy") or ""),
        },
        "focus_entity": dict(focus) if isinstance(focus, dict) else None,
        "analysis_context": analysis_context,
        "session_frame_metric": stored.get("last_metric"),
    }


def try_follow_up_governed_resolution(
    question: str,
    analysis_context: dict[str, Any],
    understanding: "TurnUnderstanding | None" = None,
) -> dict[str, Any] | None:
    if not analysis_context:
        return None
    plan = _resolve_follow_up_plan(question, analysis_context, understanding)
    if not plan:
        return None
    if plan.intent == "explain_prior_result":
        return None
    routed = _drill_metric_and_dimensions(plan, analysis_context)
    if not routed:
        return None
    metric, dimensions, predicates = routed
    dimension_mismatch: list[str] = []
    if plan.filter_entity and plan.to_grain == "material" and (
        plan.domain_id == "b2b"
        or "b2b" in str(analysis_context.get("last_metric") or "").casefold()
    ):
        dimension_mismatch = []
    payload: dict[str, Any] = {
        "status": "resolved",
        "metric": metric,
        "matched_alias": "follow_up_context",
        "dimensions": dimensions,
        "dimension_mismatch": dimension_mismatch,
        "follow_up_entity_filters": predicates,
        "follow_up_plan": {
            "intent": plan.intent,
            "to_grain": plan.to_grain,
            "limit": plan.limit,
        },
    }
    if plan.intent == "filter_entity" and plan.filter_entity and plan.filter_entity.get("id"):
        payload["follow_up_catalog_entity"] = dict(plan.filter_entity)
    return payload


def try_rewrite_follow_up_question(
    question: str,
    history: list[dict],
    understanding: "TurnUnderstanding | None" = None,
) -> str | None:
    ctx = analysis_context_from_history(history)
    if not ctx:
        return None
    plan = _resolve_follow_up_plan(question, ctx, understanding)
    if not plan:
        return None
    return build_follow_up_rewrite(question, ctx, plan)
