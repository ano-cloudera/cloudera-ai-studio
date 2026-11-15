"""The layout of an analysis is made by code from sections, so a model that writes one run-on string still gives a structured answer."""
from __future__ import annotations

from app.core.sections import AnalysisSection, SectionTable, sections_to_markdown, title_for
from app.rag.models import RagActionItem, RagLlmOutput
from app.services.rag_service import normalize_rag_llm_output


def test_headings_come_from_a_formal_vocabulary_in_the_language_of_the_answer_never_from_the_model() -> None:
    sections = [AnalysisSection(kind="detail", paragraphs=["Tiga dari delapan grup di atas nilai keseluruhan."]), AnalysisSection(kind="findings", bullets=["A unggul 18,47 poin.", "B unggul 13,6 poin."]), AnalysisSection(kind="whatever-the-model-made-up", paragraphs=["x"])]
    markdown = sections_to_markdown(sections, "id")
    assert markdown.startswith("### Penjelasan Detail\n\nTiga dari delapan")
    assert "### Temuan Utama\n\n- A unggul 18,47 poin.\n- B unggul 13,6 poin." in markdown
    assert markdown.count("### Penjelasan Detail") == 2  # an invented kind falls back to the plain explanation heading
    assert title_for("drivers", "en") == "Possible Drivers" and title_for("recommendations", "id") == "Rekomendasi Tindakan"


def test_steps_are_numbered_once_by_code_a_table_is_capped_and_an_empty_section_is_dropped() -> None:
    table = SectionTable(header=["Level", "Ambang", "Penanggung jawab", "Tenggat", "Extra"], rows=[[f"L{n}", "x", "y", "z", "dropped"] for n in range(9)])
    markdown = sections_to_markdown([AnalysisSection(kind="steps", steps=["1) Identifikasi sumber (hal. 1).", "2. Audit armada (hal. 2)."]), AnalysisSection(kind="provisions", table=table), AnalysisSection(kind="limits")], "id")
    assert "### Langkah Penanganan\n\n1. Identifikasi sumber (hal. 1).\n2. Audit armada (hal. 2)." in markdown  # the model's own numbers are not doubled
    assert "| L5 |" in markdown and "| L6 |" not in markdown  # at most six rows
    assert "Extra" not in markdown and "Batasan" not in markdown  # four columns at most; an empty section has no heading


def test_a_document_answer_is_laid_out_with_steps_a_table_and_action_items_whatever_the_model_formatted() -> None:
    out = RagLlmOutput(
        grounding="SUPPORTED",
        direct_answer="SOP Penanganan Keterlambatan mewajibkan Regional Distribution Manager membuat tiket dalam 24 jam.",
        executive_summary="Ketentuan ini berlaku untuk semua TBBM.",
        key_points=["Level 2 berlaku bila keterlambatan di atas 30% dalam satu bulan (hal. 1)."],
        steps=["1) Identifikasi sumber keterlambatan (hal. 1-2).", "Audit kesiapan armada (hal. 2)."],
        levels=SectionTable(header=["Level", "Ambang batas", "Penanggung jawab"], rows=[["Level 1", "20%", "Terminal Manager"], ["Level 2", "30%", "Regional Distribution Manager"]]),
        action_items=[RagActionItem(owner="Regional Distribution Manager", action="membuat tiket prioritas tinggi", deadline="24 jam"), RagActionItem(action="")],
    )
    answer, _, insights, implications, _ = normalize_rag_llm_output(out, "id")
    assert insights == [] and implications == []
    assert answer.startswith("SOP Penanganan Keterlambatan mewajibkan")
    assert "### Ketentuan Utama\n\n- Level 2 berlaku" in answer and "| Level 2 | 30% | Regional Distribution Manager |" in answer
    assert "### Langkah Penanganan\n\n1. Identifikasi sumber keterlambatan (hal. 1-2).\n2. Audit kesiapan armada (hal. 2)." in answer
    assert "### Tindak Lanjut\n\n- Regional Distribution Manager → membuat tiket prioritas tinggi → 24 jam" in answer  # an empty item is dropped
    english, *_ = normalize_rag_llm_output(out, "en")
    assert "### Handling Steps" in english and "### Action Items" in english
