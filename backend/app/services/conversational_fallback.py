"""Deterministic conversational answers when the LLM provider fails."""

from __future__ import annotations

from app.core.models import AnalysisOutput


def deterministic_sell_in_vs_sell_out_answer() -> dict:
    text = (
        "Inbound (sell-in) dan outbound (sell-out) mengukur sisi berbeda dari rantai distribusi. "
        "Sell-in biasanya shipment ke channel; sell-out pergerakan di sisi retail/partner. "
        "Angka keduanya tidak interchangeable tanpa definisi metric yang sama."
    )
    return AnalysisOutput(
        direct_answer=text,
        executive_summary=text,
        insights=[
            "Contoh sell-in: total billing inbound per region atau produk.",
            "Contoh sell-out: penjualan partner atau outlet per periode.",
        ],
        business_implications=[],
        caveats=["Definisi domain; tidak ada query governed di turn ini."],
        data_reference="Semantic capability definitions (no query executed).",
        chart_spec=None,
    ).model_dump()


def deterministic_promo_uplift_proxy_explain() -> dict:
    text = (
        "Proxy uplift promo membandingkan performa material atau SKU pada dua periode "
        "(misalnya bulan sebelum vs bulan promo). Ini indikator, bukan ROI promo outlet "
        "kecuali metric dan dataset secara eksplisit mendukung causal attribution."
    )
    return AnalysisOutput(
        direct_answer=text,
        executive_summary=text,
        insights=[
            "Untuk angka governed, gunakan metric uplift atau revenue yang dipublish di semantic layer.",
        ],
        business_implications=[],
        caveats=["Metodologi proxy; bukan causal attribution kecuali didefinisikan di model."],
        data_reference="Semantic methodology note (no query executed).",
        chart_spec=None,
    ).model_dump()


def deterministic_capability_follow_up_answer(
    *,
    excluded_focus: str | None,
    session_hint: dict,
    language: str = "en",
) -> dict:
    last_q = str(session_hint.get("last_question") or "").strip()
    last_metric = str(session_hint.get("last_metric") or "").strip()
    quoted = f' ("{last_q[:80]}…")' if len(last_q) > 80 else (f' ("{last_q}")' if last_q else "")
    if language == "id":
        intro = (
            "Turn sebelumnya sudah membahas analisis data"
            + (f" terkait `{last_metric}`" if last_metric else "")
            + quoted
            + ". Berikut contoh pertanyaan lain yang masih bisa ditanyakan pada semantic model yang aktif:"
        )
        note = "Contoh di `insights` mengacu metric yang dipublish; tidak ada query baru di turn ini."
    else:
        intro = (
            "The previous turn already covered a data analysis"
            + (f" on `{last_metric}`" if last_metric else "")
            + quoted
            + ". Here are other questions you can still ask on the active semantic model:"
        )
        note = "The examples in `insights` refer to published metrics; no new query ran on this turn."
    return AnalysisOutput(
        direct_answer=intro,
        executive_summary=intro,
        insights=[],
        business_implications=[],
        caveats=[note],
        data_reference="Published semantic model capability catalog (session-aware, no query executed).",
        chart_spec=None,
    ).model_dump()


def deterministic_capability_overview_answer(language: str = "en") -> dict:
    if language == "id":
        text = (
            "Saya membantu menjawab pertanyaan bisnis dengan metric dan dimensi yang dipublish "
            "di Semantic Layer (governed SQL, angka konsisten). "
            "Anda bisa mulai dengan total/KPI, breakdown per dimensi, ranking, atau trend waktu."
        )
        note = "Tidak ada query di turn ini; pilih @Semantic model lalu ajukan pertanyaan spesifik."
    else:
        text = (
            "I answer business questions using the metrics and dimensions published in the Semantic Layer "
            "(governed SQL, consistent numbers). "
            "You can start with a total or KPI, a breakdown by dimension, a ranking, or a trend over time."
        )
        note = "No query ran on this turn; pick a @Semantic model and ask a specific question."
    return AnalysisOutput(
        direct_answer=text,
        executive_summary=text,
        insights=[],
        business_implications=[],
        caveats=[note],
        data_reference="Published semantic model capability catalog (no query executed).",
        chart_spec=None,
    ).model_dump()
