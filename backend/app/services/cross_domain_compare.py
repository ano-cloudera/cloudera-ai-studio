"""Governed cross-domain compare routing (journey metrics, no runtime SQL joins)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_CONCEPT_PATTERNS: dict[str, tuple[str, ...]] = {
    "sell_in": ("sell-in", "sell in", "sellin", "general trade", "tempo ke customer", "billing tempo"),
    "sell_out": (
        "sell-out",
        "sell out",
        "sellout",
        "partner ke konsumen",
        "penjualan partner",
        "sell-out partner",
    ),
    "b2b": ("b2b", "alfamart", "partner alfamart", "penjualan b2b", "penjualan alfamart"),
    "stock_tempo": ("stock tempo", "stok tempo", "stok gudang tempo", "gudang tempo", "warehouse stock"),
    "dc_stock": ("dc stock", "dcstock", "stok dc", "stok sat", "sat dc", "penumpukan"),
    "store_stock": ("store stock", "storestock", "stok store", "stok toko", "stok retail"),
    "oos": ("oos", "out of stock", "kehabisan stok", "stok kosong"),
    "service_level": ("service level", "services level", "fill rate", "fillrate", "tingkat layanan"),
}

_COMPARE_TERMS = (
    "bandingkan",
    "banding",
    "compare",
    "perbandingan",
    "perbedaan",
    "membedakan",
    " vs ",
    "versus",
    "selisih",
    "sama atau",
    "apakah sama",
    "selaras",
    "konsisten",
    "cek juga",
    "sekaligus",
    "lintas domain",
    "big picture",
    "journey",
    "dibanding",
)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("–", "-").split())


def detect_concepts(question: str) -> set[str]:
    lowered = _normalize(question)
    words = set(re.findall(r"[a-z0-9]+", lowered))
    found: set[str] = set()
    for concept, patterns in _CONCEPT_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            found.add(concept)
    if found & {"sell_out", "b2b"}:
        found.add("sell_out")
        found.add("b2b")
    if ("stok" in words or "stock" in words) and "dc" in words:
        found.add("dc_stock")
    if ("stok" in words or "stock" in words) and bool(words & {"toko", "store", "retail"}):
        found.add("store_stock")
    if ("stok" in words or "stock" in words or "gudang" in words) and "tempo" in lowered:
        found.add("stock_tempo")
    if "penjualan" in words and "tempo" in lowered:
        found.add("sell_in")
    if "sell-in" in lowered or "sell in" in lowered:
        found.add("sell_in")
    return found


def _wants_pareto_contribution_analysis(question: str) -> bool:
    lowered = _normalize(question)
    return any(
        term in lowered
        for term in (
            "kontribusi",
            "persen kontribusi",
            "percent contribution",
            "kumulatif",
            "cumulatif",
            "cumulative",
            "nilai kumulatif",
            "pareto",
            "80/20",
            "80 20",
            "penagihan grosir",
            "nilai penagihan",
        )
    )


def wants_cross_domain_compare(question: str, *, allow_implicit_b2b_check: bool = False) -> bool:
    lowered = _normalize(question)
    if _wants_pareto_contribution_analysis(question):
        return False
    if "sekaligus" in lowered and not any(
        term in lowered for term in ("bandingkan", " vs ", "versus", "perbandingan", "selisih", "compare")
    ):
        if _wants_pareto_contribution_analysis(question):
            return False
        if not any(
            term in lowered
            for term in ("journey", "stok", "stock", "sell-out", "sell out", "sellout", "dc ")
        ):
            return False
    if any(term in lowered for term in _COMPARE_TERMS):
        return True
    if re.search(r"sell[\s-]?in.{0,40}sell[\s-]?out|sell[\s-]?out.{0,40}sell[\s-]?in", lowered):
        return True
    if allow_implicit_b2b_check and any(t in lowered for t in ("b2b", "penjualan b2b", "alfamart")):
        return True
    return False


def _entity_material_predicate(entity: dict[str, Any]) -> str | None:
    eid = str(entity.get("id") or "").strip()
    if not eid:
        return None
    lit = "'" + eid.replace("'", "''") + "'"
    dim = str(entity.get("entity_type") or entity.get("dimension") or "material")
    if dim != "material":
        return None
    return f"d.material = {lit}"


def _entity_branch_predicate(entity: dict[str, Any]) -> str | None:
    eid = str(entity.get("id") or "").strip()
    if not eid:
        return None
    lit = "'" + eid.replace("'", "''") + "'"
    dim = str(entity.get("entity_type") or entity.get("dimension") or "branch")
    if dim == "dcname":
        city = re.sub(r"^dc\s+", "", eid, flags=re.IGNORECASE).strip() or eid
        city_lit = "'" + city.replace("'", "''") + "'"
        return f"UPPER(d.branch) LIKE CONCAT('%', UPPER({city_lit}), '%')"
    if dim in ("branch", "dcname"):
        return f"(d.branch = {lit} OR UPPER(d.branch) LIKE CONCAT('%', UPPER({lit}), '%'))"
    return None


@dataclass(frozen=True)
class CrossDomainResolution:
    metric: str
    dimensions: list[str]
    matched_alias: str
    follow_up_entity_filters: list[str]


def try_resolve_cross_domain(
    question: str,
    *,
    concepts: set[str] | None = None,
    filter_entity: dict[str, Any] | None = None,
    from_grain: str | None = None,
    allow_implicit_b2b_check: bool = False,
) -> CrossDomainResolution | None:
    """Pick a published journey metric when the user asks to compare two domains."""
    if _wants_pareto_contribution_analysis(question):
        return None
    lowered = _normalize(question)
    words = set(re.findall(r"[a-z0-9]+", lowered))
    concept_set = concepts or detect_concepts(question)
    if not wants_cross_domain_compare(question, allow_implicit_b2b_check=allow_implicit_b2b_check):
        if not (filter_entity and concept_set & {"sell_out", "b2b"}):
            return None

    has_sell_in = "sell_in" in concept_set or bool(
        words & {"sellin", "sell"} and not concept_set & {"sell_out", "b2b"} and "sell-in" in lowered
    )
    if "sell-in" in lowered or "sell in" in lowered:
        has_sell_in = True
    has_sell_out = bool(concept_set & {"sell_out", "b2b"})
    has_stock_tempo = "stock_tempo" in concept_set
    has_dc_stock = "dc_stock" in concept_set
    has_store_stock = "store_stock" in concept_set
    has_oos = "oos" in concept_set

    material_focus = (
        from_grain == "material"
        or bool(words & {"material", "produk", "sku", "plu", "item"})
        or (
            filter_entity is not None
            and str(filter_entity.get("dimension") or filter_entity.get("entity_type") or "") == "material"
        )
    )
    branch_focus = (
        from_grain in ("branch", "dcname")
        or bool(words & {"cabang", "branch", "dc"})
        or (
            filter_entity is not None
            and str(filter_entity.get("dimension") or filter_entity.get("entity_type") or "") in ("branch", "dcname")
        )
    )

    predicates: list[str] = []
    if filter_entity:
        mat_pred = _entity_material_predicate(filter_entity)
        if mat_pred:
            predicates.append(mat_pred)
        branch_pred = _entity_branch_predicate(filter_entity)
        if branch_pred and not mat_pred:
            predicates.append(branch_pred)

    if has_sell_in and has_sell_out:
        if material_focus:
            return CrossDomainResolution(
                metric="material_sell_out_to_sell_in_value_ratio",
                dimensions=["material"],
                matched_alias="cross_domain_sell_in_b2b_material",
                follow_up_entity_filters=predicates,
            )
        if branch_focus and (has_dc_stock or "stok" in words):
            return CrossDomainResolution(
                metric="branch_sell_out_vs_dc_stock",
                dimensions=["branch"],
                matched_alias="cross_domain_b2b_dc_stock_branch",
                follow_up_entity_filters=predicates,
            )
        return CrossDomainResolution(
            metric="sell_out_to_sell_in_value_ratio",
            dimensions=[],
            matched_alias="cross_domain_sell_in_b2b_aggregate",
            follow_up_entity_filters=[],
        )

    if has_stock_tempo and has_sell_in and material_focus:
        dims = ["calmonth", "material"] if any(t in lowered for t in ("per bulan", "bulanan", "tren", "trend")) else ["material"]
        return CrossDomainResolution(
            metric="stock_tempo_to_sell_in_ratio",
            dimensions=dims,
            matched_alias="cross_domain_stock_tempo_sell_in",
            follow_up_entity_filters=predicates,
        )

    if has_dc_stock and has_sell_out and branch_focus:
        return CrossDomainResolution(
            metric="branch_sell_out_vs_dc_stock",
            dimensions=["branch"],
            matched_alias="cross_domain_dc_stock_sell_out",
            follow_up_entity_filters=predicates,
        )

    if has_dc_stock and has_store_stock:
        return CrossDomainResolution(
            metric="sat_dc_stock_quantity",
            dimensions=["dcname"],
            matched_alias="cross_domain_dc_vs_store_stock",
            follow_up_entity_filters=predicates,
        )

    if has_oos and (has_dc_stock or has_store_stock):
        dims = ["plu"]
        if "dc" in words:
            dims.append("dcname")
        return CrossDomainResolution(
            metric="sat_oos_rate",
            dimensions=dims,
            matched_alias="cross_domain_stock_oos",
            follow_up_entity_filters=predicates,
        )

    # Follow-up: prior sell-in material + B2B check without repeating "bandingkan"
    if filter_entity and has_sell_out and from_grain == "material":
        return CrossDomainResolution(
            metric="material_sell_out_to_sell_in_value_ratio",
            dimensions=["material"],
            matched_alias="cross_domain_follow_up_material_b2b",
            follow_up_entity_filters=predicates,
        )

    return None


def resolution_to_payload(resolution: CrossDomainResolution) -> dict[str, Any]:
    return {
        "status": "resolved",
        "metric": resolution.metric,
        "matched_alias": resolution.matched_alias,
        "dimensions": list(resolution.dimensions),
        "dimension_mismatch": [],
        "follow_up_entity_filters": list(resolution.follow_up_entity_filters),
    }
