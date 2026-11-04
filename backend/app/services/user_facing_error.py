from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.language import detect_language
from app.core.models import AnalysisOutput
from app.llm.base import LLMProvider, ProviderError


logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _fallback_answer(failure: dict[str, Any], *, request_id: str) -> AnalysisOutput:
    kind = str(failure.get("kind") or "internal")
    code = str(failure.get("code") or "")
    question = str(failure.get("question") or "").strip()

    if detect_language(question) != "id":
        return _fallback_answer_en(kind=kind, code=code, question=question, request_id=request_id)

    if code == "IMPALA_AUTH_FAILED":
        direct = (
            "Saat ini saya tidak bisa mengakses data Impala karena sesi autentikasi backend belum valid."
        )
        summary = (
            "Ini masalah koneksi/akun di sisi server, bukan karena pertanyaan Anda salah. "
            "Operator perlu memastikan profil LDAP atau ticket Kerberos pada environment aplikasi."
        )
        caveats = [
            f"Request ID: {request_id}.",
            "Setelah autentikasi diperbaiki, silakan ajukan pertanyaan yang sama lagi.",
        ]
    elif code == "QUERY_REJECTED":
        direct = "Sumber data menolak query yang disusun untuk pertanyaan ini, jadi saya belum bisa menjawabnya."
        summary = (
            "Koneksi ke sumber data baik. Yang bermasalah adalah isi query, misalnya kolom yang tidak ditemukan atau perhitungan yang tidak valid. "
            "Coba tulis ulang pertanyaan dengan lebih spesifik, atau minta operator memeriksa SQL di bawah."
        )
        caveats = [f"Request ID: {request_id}."]
    elif code == "IMPALA_QUERY_FAILED":
        direct = (
            "Query ke data warehouse tidak selesai, kemungkinan karena beban cluster, timeout, "
            "atau filter yang terlalu sempit untuk periode Q4 2024."
        )
        summary = (
            "Pertanyaan Anda sudah diproses, tetapi eksekusi di Impala gagal. "
            "Coba sederhanakan scope (misalnya top 10, satu metrik, atau periode lebih pendek) "
            "atau ulangi beberapa saat lagi."
        )
        caveats = [f"Request ID: {request_id}."]
    elif kind == "sql_validation":
        direct = (
            "Saya tidak bisa menjalankan query otomatis untuk pertanyaan ini karena rencana SQL "
            "tidak lolos pemeriksaan keamanan governed (kolom/tabel/join yang tidak disetujui)."
        )
        summary = (
            "Biasanya ini terjadi pada pertanyaan multi-konsep atau wording yang mendorong SQL di luar "
            "katalog metrik REFERENCE. Coba pecah pertanyaan per metrik (misalnya picking vs unloading "
            "terpisah) atau pilih opsi klarifikasi Sell-In/Sell-Out bila diminta."
        )
        caveats = [f"Request ID: {request_id}."]
    elif kind == "provider":
        direct = (
            "Model analisis sementara tidak merespons, jadi saya belum bisa menyelesaikan langkah "
            "perencanaan atau rangkuman untuk pertanyaan Anda."
        )
        summary = (
            "Ini gangguan sementara di layanan LLM, bukan indikasi data Anda tidak ada. "
            "Silakan kirim ulang pertanyaan dalam 1–2 menit."
        )
        caveats = [f"Request ID: {request_id}."]
    else:
        direct = (
            "Maaf, permintaan ini belum bisa saya selesaikan dengan aman di backend."
        )
        summary = (
            "Tim operator dapat menelusuri jejak server dengan request ID di bawah. "
            "Anda tetap bisa mencoba ulang dengan pertanyaan yang lebih spesifik "
            "(metrik, periode Q4 2024, top N)."
        )
        caveats = [f"Request ID: {request_id}."]

    if question:
        caveats.insert(0, f"Pertanyaan: {question[:240]}{'…' if len(question) > 240 else ''}")

    return AnalysisOutput(
        direct_answer=direct,
        executive_summary=summary,
        insights=[],
        business_implications=[],
        caveats=caveats,
        data_reference="No result available.",
        chart_spec=None,
    )


def _fallback_answer_en(*, kind: str, code: str, question: str, request_id: str) -> AnalysisOutput:
    if code in ("IMPALA_AUTH_FAILED", "CONNECTOR_AUTH_FAILED"):
        direct = "I can't reach the data source right now because the backend's authentication session is not valid."
        summary = (
            "This is a connection or account issue on the server side, not a problem with your question. "
            "An operator needs to check the credentials configured for the data connector."
        )
        caveats = [f"Request ID: {request_id}.", "Once authentication is fixed, please ask the same question again."]
    elif code == "QUERY_REJECTED":
        direct = "The data source rejected the query that was built for this question, so I could not answer it yet."
        summary = (
            "The connection is fine. The problem is in the query itself, for example a column that was not found or a calculation that is not valid. "
            "Try rephrasing the question more specifically, or ask an operator to check the SQL below."
        )
        caveats = [f"Request ID: {request_id}."]
    elif code == "IMPALA_QUERY_FAILED":
        direct = "The query to the data warehouse did not complete, possibly because of cluster load, a timeout, or a filter that is too narrow."
        summary = (
            "Your question was processed, but the query failed to run. "
            "Try simplifying the scope (for example a top 10, a single metric, or a shorter period) "
            "or try again in a moment."
        )
        caveats = [f"Request ID: {request_id}."]
    elif kind == "sql_validation":
        direct = (
            "I can't run an automatic query for this question because the SQL plan did not pass the governed safety check "
            "(columns, tables, or joins that are not approved)."
        )
        summary = (
            "This usually happens with multi-concept questions or wording that pushes the SQL outside the published "
            "metrics. Try splitting the question by metric, or pick a clarification option when one is offered."
        )
        caveats = [f"Request ID: {request_id}."]
    elif kind == "provider":
        direct = (
            "The analysis model is not responding right now, so I could not finish planning or summarizing your question."
        )
        summary = "This is a temporary issue with the LLM service, not a sign that your data is missing. Please resend the question in a minute or two."
        caveats = [f"Request ID: {request_id}."]
    else:
        direct = "Sorry, I could not complete this request safely on the backend."
        summary = (
            "An operator can trace the server logs using the request ID below. "
            "You can still try again with a more specific question (a metric, a period, a top N)."
        )
        caveats = [f"Request ID: {request_id}."]
    if question:
        caveats.insert(0, f"Question: {question[:240]}{'…' if len(question) > 240 else ''}")
    return AnalysisOutput(
        direct_answer=direct,
        executive_summary=summary,
        insights=[],
        business_implications=[],
        caveats=caveats,
        data_reference="No result available.",
        chart_spec=None,
    )


def _with_technical_reason(answer: AnalysisOutput, failure: dict[str, Any], question: str) -> AnalysisOutput:
    """The kind and code of the failure (never the driver message), so an operator can tell failures apart from the PDF."""
    kind, code = str(failure.get("kind") or "").strip(), str(failure.get("code") or "").strip()
    if not kind and not code:
        return answer
    label = f"{kind}/{code}" if kind and code else (kind or code)
    language = detect_language(question)
    line = f"Rincian teknis: {label}." if language == "id" else f"Technical reason: {label}."
    return answer.model_copy(update={"caveats": [*answer.caveats, line]})


async def explain_failure(
    *,
    provider: LLMProvider | None,
    question: str,
    failure: dict[str, Any],
    request_id: str,
) -> AnalysisOutput:
    """Natural-language ERROR body; never leaks driver or validator internals."""
    logger.warning(
        "ask_data_failure request_id=%s kind=%s code=%s detail=%s",
        request_id,
        failure.get("kind"),
        failure.get("code"),
        str(failure.get("detail") or "")[:500],
    )
    payload = {
        "question": question,
        "request_id": request_id,
        "failure": failure,
        "answer_language": "Indonesian" if detect_language(question) == "id" else "English",
    }
    if provider is None:
        return _with_technical_reason(_fallback_answer({**failure, "question": question}, request_id=request_id), failure, question)

    try:
        return _with_technical_reason(await provider.generate_structured(
            [
                {"role": "system", "content": _prompt("global_system.md") + "\n" + _prompt("user_facing_error.md")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            AnalysisOutput,
            temperature=0.3,
            max_tokens=900,
        ), failure, question)
    except ProviderError:
        logger.warning(
            "user_facing_error_llm_failed request_id=%s failure_kind=%s failure_code=%s",
            request_id,
            failure.get("kind"),
            failure.get("code"),
        )
        return _with_technical_reason(_fallback_answer({**failure, "question": question}, request_id=request_id), failure, question)
