from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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
            "katalog metrik TEMPO. Coba pecah pertanyaan per metrik (misalnya picking vs unloading "
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


async def explain_failure(
    *,
    provider: LLMProvider | None,
    question: str,
    failure: dict[str, Any],
    request_id: str,
) -> AnalysisOutput:
    """Natural-language ERROR body; never leaks driver or validator internals."""
    payload = {
        "question": question,
        "request_id": request_id,
        "failure": failure,
        "scope": "TEMPO commercial analytics Q4 2024 (Oct–Dec 2024)",
    }
    if provider is None:
        return _fallback_answer({**failure, "question": question}, request_id=request_id)

    try:
        return await provider.generate_structured(
            [
                {"role": "system", "content": _prompt("global_system.md") + "\n" + _prompt("user_facing_error.md")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            AnalysisOutput,
            temperature=0.3,
            max_tokens=900,
        )
    except ProviderError:
        logger.warning(
            "user_facing_error_llm_failed request_id=%s failure_kind=%s failure_code=%s",
            request_id,
            failure.get("kind"),
            failure.get("code"),
        )
        return _fallback_answer({**failure, "question": question}, request_id=request_id)
