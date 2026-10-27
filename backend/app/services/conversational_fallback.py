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
) -> dict:
    last_q = str(session_hint.get("last_question") or "").strip()
    last_metric = str(session_hint.get("last_metric") or "").strip()
    intro = (
        "Turn sebelumnya sudah membahas analisis data"
        + (f" terkait `{last_metric}`" if last_metric else "")
        + (f' ("{last_q[:80]}…")' if len(last_q) > 80 else (f' ("{last_q}")' if last_q else ""))
        + ". Berikut contoh pertanyaan lain yang masih bisa ditanyakan pada semantic model yang aktif:"
    )
    return AnalysisOutput(
        direct_answer=intro,
        executive_summary=intro,
        insights=[],
        business_implications=[],
        caveats=[
            "Contoh di `insights` mengacu metric yang dipublish; tidak ada query baru di turn ini.",
        ],
        data_reference="Published semantic model capability catalog (session-aware, no query executed).",
        chart_spec=None,
    ).model_dump()


def deterministic_capability_overview_answer() -> dict:
    text = (
        "Saya membantu menjawab pertanyaan bisnis dengan metric dan dimensi yang dipublish "
        "di Semantic Layer (governed SQL, angka konsisten). "
        "Anda bisa mulai dengan total/KPI, breakdown per dimensi, ranking, atau trend waktu."
    )
    return AnalysisOutput(
        direct_answer=text,
        executive_summary=text,
        insights=[],
        business_implications=[],
        caveats=["Tidak ada query di turn ini; pilih @Semantic model lalu ajukan pertanyaan spesifik."],
        data_reference="Published semantic model capability catalog (no query executed).",
        chart_spec=None,
    ).model_dump()
