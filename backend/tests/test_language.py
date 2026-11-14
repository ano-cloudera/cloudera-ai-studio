from __future__ import annotations

import pytest

from app.core.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How many credit applications do we have in total?", "en"),
        ("What is our delinquency rate in Q3 2026?", "en"),
        ("Compare the approval rate by region and channel from June to August 2026.", "en"),
        ("Berapa total aplikasi kredit kita?", "id"),
        ("Bandingkan approval rate per wilayah dan channel selama Juni sampai Agustus 2026.", "id"),
        ("total approval rate", "en"),
        ("selamat pagi", "id"),
        ("halo", "id"),
        ("hallo kamu bisa bantu apa bisa apa ?", "id"),
        ("terima kasih", "id"),
        ("hello", "en"),
        ("hi, what can you help with?", "en"),
        ("good morning", "en"),
        ("Berapa pencapaian kuota per terminal?", "id"),
        ("Pendapatan per loyalty tier", "id"),
        ("Tampilkan volume penyaluran per provinsi", "id"),
        ("Regional mana yang paling sering terlambat?", "id"),
        ("Gimana kondisi penyaluran BBM kita secara keseluruhan?", "id"),
        ("Total Revenue per month", "en"),
        ("Revenue per region", "en"),
        ("What is the late rate per region?", "en"),
        ("", "en"),
        (None, "en"),
    ],
)
def test_detect_language_defaults_to_english(text, expected):
    assert detect_language(text) == expected


def test_rag_insufficient_message_follows_the_question_language() -> None:
    from types import SimpleNamespace

    from app.rag.prompt import INSUFFICIENT_ANSWER_EN, INSUFFICIENT_ANSWER_ID, load_rag_insufficient_message

    settings = SimpleNamespace(rag_system_prompt_path=None)
    english = load_rag_insufficient_message(settings, question="When is a segment flagged for investigation?")
    indonesian = load_rag_insufficient_message(settings, question="Kapan segmen ditandai untuk investigasi?")
    assert english == INSUFFICIENT_ANSWER_EN
    assert indonesian == INSUFFICIENT_ANSWER_ID


def test_the_document_prompt_names_the_answer_language_from_the_question() -> None:
    from app.rag.prompt import build_rag_user_message

    indonesian = build_rag_user_message(question="Apa yang harus dilakukan kalau keterlambatan TBBM di atas 30%?", evidence=[], dialog=[], language="id")
    english = build_rag_user_message(question="What must be done when TBBM delay exceeds 30%?", evidence=[], dialog=[], language="en")
    assert "Answer language: Indonesian" in indonesian
    assert "Answer language: English" in english
    assert "Answer language" not in build_rag_user_message(question="x", evidence=[], dialog=[])  # without a language nothing is claimed
