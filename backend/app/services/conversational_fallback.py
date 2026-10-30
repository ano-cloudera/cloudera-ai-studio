"""Deterministic conversational answers when the LLM provider fails."""

from __future__ import annotations

from app.core.models import AnalysisOutput




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
