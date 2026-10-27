"""Session memory helpers for analytic follow-ups (SQLite history + last query rows)."""

from __future__ import annotations

import re
from typing import Any

_BRANCH_CODE_RE = re.compile(r"\b(0\d{3})\b")

_TOP_ONE_RE = re.compile(r"\btop\s*(?:1|satu)\b", re.IGNORECASE)

_DRILL_REFERENTIAL_MARKERS = (
    "itu",
    "ini",
    "tersebut",
    "tadi",
    "dari data",
    "dari grafik",
    "dari chart",
    "dari tabel",
    "yang paling",
    "paling jelek",
    "terjelek",
    "terburuk",
    "terendah",
    "lanjut",
    "drill",
    "detail",
    "based on",
    "berdasarkan",
    "kenapa",
    "mengapa",
    "penyebab",
    "breakdown",
    "per material",
    "per produk",
    "pertama",
    "rank",
    "urutan",
    "hasil itu",
    "ranking itu",
    "lebih lambat",
    "selisih",
    "mana yang",
    "kelima",
    "ke lima",
    "ke limat",
    "terakhir",
    "dominan",
    "status dominan",
)

_COMPARE_REFERENTIAL_MARKERS = (
    "bandingkan",
    "banding",
    "compare",
    "perbedaan",
    "membedakan",
    "beda",
    "perbandingan",
)

_RANK_COMPARE_HINTS = (
    "pertama",
    "terakhir",
    "kelima",
    "ke lima",
    "rank",
    "urutan",
    "paling atas",
    "paling bawah",
    "teratas",
    "terbawah",
)

_ENTITY_KEYS = (
    "sales_off",
    "sales_office",
    "material",
    "material_code",
    "dcname",
    "branch",
    "customer",
    "plu",
    "plant",
    "division",
    "e_store",
    "cust_id",
    "program_status",
    "fill_rate_band",
)


def is_referential_follow_up(question: str) -> bool:
    """True when the user likely refers to the prior turn (not a fresh UAT prompt)."""
    normalized = " ".join(question.casefold().replace("–", "-").split())
    if _TOP_ONE_RE.search(normalized):
        return True
    if any(marker in normalized for marker in _DRILL_REFERENTIAL_MARKERS):
        return True
    if any(marker in normalized for marker in _COMPARE_REFERENTIAL_MARKERS):
        return any(hint in normalized for hint in _RANK_COMPARE_HINTS)
    return False


def build_session_frame(
    *,
    question: str,
    status: str,
    strategy: str,
    rows: list[dict],
    metric: str | None = None,
    dimensions: list[str] | None = None,
) -> dict[str, Any]:
    from app.services.follow_up import build_analysis_context
    """Persist compact analytic context for chart/table follow-ups."""
    if status not in ("SUCCESS", "NO_DATA") or strategy not in ("governed", "sql_fallback"):
        return {}
    if not rows:
        return {}
    ranked = _ranked_entities_from_rows(rows, preferred_dimensions=list(dimensions or []))
    entity_dimension = ranked[0]["dimension"] if ranked else None
    if not entity_dimension and dimensions:
        entity_dimension = str(dimensions[0])
    analysis_context = build_analysis_context(
        metric=metric,
        dimensions=list(dimensions or []),
        entity_dimension=entity_dimension,
        ranked_entities=ranked,
        last_question=question.strip(),
    )
    return {
        "last_question": question.strip(),
        "last_status": status,
        "last_strategy": strategy,
        "last_metric": metric,
        "last_dimensions": list(dimensions or []),
        "entity_dimension": entity_dimension,
        "ranked_entities": ranked,
        "row_count": len(rows),
        "analysis_context": analysis_context,
    }


def _ranked_entities_from_rows(
    rows: list[dict],
    *,
    preferred_dimensions: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    dimension: str | None = None
    first = rows[0] if isinstance(rows[0], dict) else {}
    for key in preferred_dimensions or []:
        if first.get(key) not in (None, ""):
            dimension = key
            break
    if not dimension:
        for key in _ENTITY_KEYS:
            if first.get(key) not in (None, ""):
                dimension = key
                break
    ranked: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:25]):
        if not isinstance(row, dict):
            continue
        entity_id: str | None = None
        if dimension:
            value = row.get(dimension)
            if value not in (None, ""):
                entity_id = str(value)
        if not entity_id:
            entity_id = _row_entity_id(row)
        if not entity_id:
            continue
        item: dict[str, Any] = {
            "rank": index + 1,
            "dimension": dimension,
            "id": entity_id,
        }
        if row.get("metric_value") is not None:
            item["metric_value"] = row["metric_value"]
        ranked.append(item)
    return ranked


def _is_governed_data_turn(entry: dict) -> bool:
    if entry.get("strategy") not in ("governed", "sql_fallback"):
        return False
    if entry.get("status") not in ("SUCCESS", "NO_DATA"):
        return False
    return len(_rows_for_chart_follow_up(entry)) >= 2


def _last_governed_chart_turn(history: list[dict]) -> dict | None:
    """Most recent turn with a ranked table/chart, skipping ERROR/clarification turns."""
    for entry in reversed(history):
        if _is_governed_data_turn(entry):
            return entry
    return None


def _last_governed_success_turn(history: list[dict]) -> dict | None:
    """Most recent governed/sql_fallback SUCCESS turn with at least one data row."""
    for entry in reversed(history):
        if entry.get("strategy") not in ("governed", "sql_fallback"):
            continue
        if entry.get("status") != "SUCCESS":
            continue
        if _rows_for_chart_follow_up(entry):
            return entry
    return None


def infer_governed_metric_from_turn(entry: dict, *, ranked_entities: list[dict[str, Any]]) -> str | None:
    """Best-effort metric when SQLite history lacks session_frame (older turns)."""
    stored = entry.get("session_frame") if isinstance(entry.get("session_frame"), dict) else {}
    last_metric = stored.get("last_metric")
    if isinstance(last_metric, str) and last_metric.strip():
        return last_metric.strip()
    question = str(entry.get("question") or "").casefold()
    dimension = None
    if ranked_entities and isinstance(ranked_entities[0], dict):
        dimension = ranked_entities[0].get("dimension") or ranked_entities[0].get("entity_type")
    if dimension == "branch" or any(
        isinstance(row, dict) and row.get("branch") not in (None, "") for row in _rows_for_chart_follow_up(entry)
    ):
        b2b_hints = (
            "b2b",
            "sell-out",
            "sell out",
            "sellout",
            "dc ",
            "alfamart",
            "partner",
            "konsumen akhir",
            "estore",
            "e-store",
        )
        if any(hint in question for hint in b2b_hints):
            return "b2b_branch_sell_out_value"
    if dimension in ("sales_off", "sales_office"):
        return "sales_office_sell_in_value"
    if dimension == "material":
        if any(hint in question for hint in ("b2b", "sell-out", "sell out", "alfamart")):
            return "b2b_material_plu_value"
        return "material_sell_in_value"
    if dimension == "dcname":
        return "sat_dc_stock_quantity"
    return None


def _rows_for_chart_follow_up(entry: dict) -> list[dict[str, Any]]:
    stored = entry.get("session_frame")
    if isinstance(stored, dict) and stored.get("ranked_entities"):
        synthetic: list[dict[str, Any]] = []
        for item in stored["ranked_entities"]:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            dim = item.get("dimension") or "sales_office"
            row: dict[str, Any] = {str(dim): item["id"]}
            if item.get("metric_value") is not None:
                row["metric_value"] = item["metric_value"]
            synthetic.append(row)
        if synthetic:
            return synthetic
    rows = entry.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def capability_session_hint(history: list[dict]) -> dict[str, Any]:
    """Compact prior-turn context for conversational capability / “what else?” answers."""
    if not history:
        return {}
    from app.services.follow_up import analysis_context_from_history

    ctx = analysis_context_from_history(history)
    last = history[-1]
    answer = last.get("answer") if isinstance(last.get("answer"), dict) else {}
    metrics_seen: list[str] = []
    for item in history[-6:]:
        frame = item.get("session_frame") if isinstance(item.get("session_frame"), dict) else {}
        metric = frame.get("last_metric")
        if isinstance(metric, str) and metric and metric not in metrics_seen:
            metrics_seen.append(metric)
    return {
        "last_metric": ctx.get("last_metric"),
        "last_question": str(last.get("question") or "").strip(),
        "last_answer_excerpt": _answer_excerpt(last),
        "active_grain": ctx.get("active_grain"),
        "metrics_seen_in_session": metrics_seen,
        "turn_count": len(history),
    }


def session_frame_from_history(history: list[dict]) -> dict[str, Any]:
    """Structured slice of the last turn for governed rewrites (not raw LLM dump)."""
    if not history:
        return {}
    last = history[-1]
    stored = last.get("session_frame") if isinstance(last.get("session_frame"), dict) else {}
    frame: dict[str, Any] = {
        "prior_question": str(last.get("question") or stored.get("last_question") or "").strip(),
        "prior_answer_excerpt": _answer_excerpt(last),
        "last_metric": stored.get("last_metric"),
        "last_dimensions": stored.get("last_dimensions") or [],
        "ranked_entities": stored.get("ranked_entities") or [],
    }
    follow_up_rows = _rows_for_chart_follow_up(last)
    row = follow_up_rows[0] if follow_up_rows else _first_data_row(last)
    if row:
        frame["top_row"] = row
        for key in _ENTITY_KEYS:
            value = row.get(key)
            if value not in (None, ""):
                frame.setdefault("entities", {})[key] = str(value)
    branch = _BRANCH_CODE_RE.search(frame["prior_answer_excerpt"])
    if branch:
        frame.setdefault("entities", {})["sales_off"] = branch.group(1)
    return frame


def _first_data_row(entry: dict) -> dict[str, Any] | None:
    rows = entry.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    first = rows[0]
    return first if isinstance(first, dict) else None


def _row_entity_id(row: dict[str, Any]) -> str | None:
    for key in _ENTITY_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _comparison_rank_indices(question: str, row_count: int) -> tuple[int, int] | None:
    normalized = " ".join(question.casefold().replace("–", "-").split())
    explicit_compare = any(
        term in normalized
        for term in ("bandingkan", "banding", "compare", "perbedaan", "membedakan", "beda", " vs ")
    )
    implicit_rank_pair = (
        any(term in normalized for term in ("paling tinggi", "tertinggi", "terbesar", "paling atas"))
        and any(term in normalized for term in ("paling rendah", "terendah", "terkecil", "paling kecil", "paling bawah"))
    )
    if not explicit_compare and not implicit_rank_pair:
        return None
    if row_count < 2:
        return None
    explicit_pair = re.search(
        r"\burutan\s*(\d+)\s*(?:dan|dengan|vs|&|serta)\s*urutan\s*(\d+)\b",
        normalized,
    )
    if explicit_pair:
        a = min(max(int(explicit_pair.group(1)) - 1, 0), row_count - 1)
        b = min(max(int(explicit_pair.group(2)) - 1, 0), row_count - 1)
        if a != b:
            return a, b
    first_idx = 0
    second_idx = min(4, row_count - 1)
    if any(term in normalized for term in ("kelima", "ke lima", "ke limat", "urutan 5", "rank 5")):
        second_idx = min(4, row_count - 1)
    elif any(
        term in normalized
        for term in ("terakhir", "paling bawah", "paling rendah", "terendah", "terkecil", "paling kecil")
    ):
        second_idx = row_count - 1
    elif re.search(r"\b(?:rank|urutan)\s*(\d+)", normalized):
        match = re.search(r"\b(?:rank|urutan)\s*(\d+)", normalized)
        if match:
            second_idx = min(max(int(match.group(1)) - 1, 0), row_count - 1)
    if any(
        term in normalized
        for term in ("pertama", "paling atas", "teratas", "paling tinggi", "tertinggi", "terbesar", "rank 1", "urutan 1")
    ):
        first_idx = 0
    if first_idx == second_idx and row_count > 1:
        second_idx = row_count - 1
    return first_idx, second_idx


def _rewrite_rank_comparison_from_chart(question: str, history: list[dict]) -> str | None:
    """Compare row #1 vs #N from the last governed result set (chart/table follow-up)."""
    anchor = _last_governed_chart_turn(history)
    if anchor is None:
        return None
    rows = _rows_for_chart_follow_up(anchor)
    if len(rows) < 2:
        return None
    ranks = _comparison_rank_indices(question, len(rows))
    if ranks is None:
        return None
    idx_a, idx_b = ranks
    entity_a = _row_entity_id(rows[idx_a])
    entity_b = _row_entity_id(rows[idx_b])
    if not entity_a or not entity_b:
        return None
    prior_q = str(anchor.get("question") or "").casefold()
    prior_text = _answer_excerpt(anchor).casefold()
    sell_out = _question_prefers_sell_out_from_text(f"{prior_q} {prior_text} {question}")
    if sell_out:
        grain = "branch partner B2B"
        metric_hint = "nilai sell-out B2B"
    else:
        grain = "sales office Tempo (sell-in)"
        metric_hint = "nilai sell-in gross billing"
    return (
        f"Q4 2024, bandingkan {grain} {entity_a} vs {entity_b}: "
        f"tampilkan total {metric_hint} masing-masing cabang dan "
        f"10 material/produk dengan kontribusi penjualan terbesar per cabang "
        f"untuk menjelaskan perbedaan performa. "
        f"Pertanyaan asli pengguna: {question.strip()}"
    )


def _question_prefers_sell_out_from_text(text: str) -> bool:
    lowered = text.casefold()
    sell_in = any(term in lowered for term in ("sell-in", "sell in", "klarifikasi pengguna: sell-in"))
    sell_out = any(term in lowered for term in ("sell-out", "sell out", "b2b", "partner"))
    return sell_out and not sell_in


def _answer_excerpt(entry: dict, *, max_len: int = 400) -> str:
    answer = entry.get("answer") or {}
    text = " ".join(
        part
        for part in (
            str(answer.get("direct_answer") or ""),
            str(answer.get("executive_summary") or ""),
        )
        if part
    ).strip()
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def answer_offers_clarification_choice(clarification: str) -> bool:
    offered = clarification.casefold().replace("–", "-")
    return (
        ("sell-in" in offered and "sell-out" in offered)
        or ("dc stock" in offered and "store stock" in offered)
        or ("stok dc" in offered and "stok store" in offered)
        or ("stok gudang tempo" in offered and ("stok dc" in offered or "stok retail" in offered))
        or ("proxy" in offered and "promo" in offered and "metrik mana" in offered)
        or ("picking" in offered and "unloading" in offered and "metrik" in offered)
        or (" atau " in f" {offered} " and "?" in clarification)
    )


def last_turn_awaiting_clarification(history: list[dict]) -> bool:
    """True when the prior turn expects a chip/short choice, not a new UAT prompt."""
    if not history:
        return False
    last = history[-1]
    if last.get("strategy") == "clarification" or last.get("status") == "CLARIFICATION":
        return True
    rows = last.get("rows")
    if isinstance(rows, list) and rows:
        return False
    answer = last.get("answer") or {}
    text = " ".join(
        part
        for part in (
            str(answer.get("direct_answer") or ""),
            str(answer.get("executive_summary") or ""),
            " ".join(str(item) for item in answer.get("insights") or []),
        )
        if part
    ).strip()
    return bool(text) and answer_offers_clarification_choice(text)


def rewrite_referential_analytic_question(question: str, history: list[dict]) -> str | None:
    """Governed-friendly rewrite using session frame; None if no safe rewrite."""
    if not history:
        return None
    chart_compare = _rewrite_rank_comparison_from_chart(question, history)
    if chart_compare:
        return chart_compare
    if not is_referential_follow_up(question):
        return None
    frame = session_frame_from_history(history)
    prior_q = frame.get("prior_question", "").casefold()
    prior_text = frame.get("prior_answer_excerpt", "").casefold()
    entities = frame.get("entities") or {}
    normalized = " ".join(question.casefold().replace("–", "-").split())

    service_context = any(
        term in prior_q or term in prior_text
        for term in ("fill rate", "service level", "fillrate", "pemenuhan")
    )
    branch = entities.get("sales_off") or entities.get("sales_office")
    if service_context and branch and any(t in normalized for t in ("kenapa", "analisa", "penyebab", "mengapa", "jelek", "terendah")):
        return (
            f"Untuk sales office {branch} (cabang Tempo) pada Q4 2024, "
            f"tampilkan 10 material dengan fill rate / service level terendah "
            f"dan selisih quantity PO vs DO terbesar (breakdown per material). "
            f"Pertanyaan asli pengguna: {question.strip()}"
        )

    if service_context and (_TOP_ONE_RE.search(normalized) or any(t in normalized for t in ("paling jelek", "terjelek"))) and not branch:
        return (
            f"Lanjutan analisis service level cabang Tempo Q4 2024: "
            f"{question.strip()} "
            f"(gunakan konteks jawaban sebelumnya: {frame.get('prior_answer_excerpt', '')})"
        )

    from app.services.follow_up import try_rewrite_follow_up_question

    contextual = try_rewrite_follow_up_question(question, history)
    if contextual:
        return contextual
    return None
