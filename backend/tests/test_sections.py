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
    assert markdown.count("### Penjelasan Detail") == 1  # an invented kind falls back to the plain explanation, under the same heading
    assert markdown.index("Tiga dari delapan") < markdown.index("\n\nx")  # and its text follows the first paragraph
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


def test_an_action_item_without_an_owner_or_a_deadline_is_not_shown_again_under_follow_up() -> None:
    out = RagLlmOutput(
        grounding="SUPPORTED",
        direct_answer="Rekening yang dipakai 3 peserta atau lebih dianggap tanda bahaya.",
        executive_summary="Berlaku untuk semua klaim penggantian biaya.",
        steps=["Verifikasi kuitansi (hal. 2).", "Konfirmasi ke penyedia (hal. 2).", "Analisis keterkaitan klaim (hal. 2)."],
        action_items=[RagActionItem(action="Verifikasi kuitansi"), RagActionItem(owner="SIU", action="memeriksa klaim", deadline="2 hari kerja")],
    )
    answer, *_ = normalize_rag_llm_output(out, "id")
    assert "Verifikasi kuitansi\n" not in answer.split("### Tindak Lanjut")[-1]
    assert "- SIU → memeriksa klaim → 2 hari kerja" in answer
    only_repeats = out.model_copy(update={"action_items": [RagActionItem(action="Verifikasi kuitansi")]})
    answer, *_ = normalize_rag_llm_output(only_repeats, "id")
    assert "Tindak Lanjut" not in answer


def test_a_lone_section_has_no_heading_in_a_document_answer_but_several_keep_theirs() -> None:
    steps = AnalysisSection(kind="steps", steps=["Verifikasi kuitansi (hal. 2).", "Konfirmasi ke penyedia (hal. 2)."])
    points = AnalysisSection(kind="provisions", bullets=["Ambang 3 peserta (hal. 1)."])
    assert sections_to_markdown([steps], "id", lone_heading=False) == "1. Verifikasi kuitansi (hal. 2).\n2. Konfirmasi ke penyedia (hal. 2)."
    assert sections_to_markdown([steps], "id").startswith("### Langkah Penanganan")  # the analysis keeps its heading
    both = sections_to_markdown([points, steps], "id", lone_heading=False)
    assert "### Ketentuan Utama" in both and "### Langkah Penanganan" in both


def test_the_laid_out_analysis_and_the_recommendations_carry_no_em_dash() -> None:
    from app.core.models import ActionRecommendation

    markdown = sections_to_markdown([AnalysisSection(kind="findings", bullets=["Kertapati turun \u2014 Panjang naik"])], "id")
    assert "\u2014" not in markdown
    row = ActionRecommendation(action="Alihkan armada \u2014 sementara", basis="2.056 KL \u2014 Agustus")
    assert "\u2014" not in row.action and "\u2014" not in row.basis


def test_a_kind_used_several_times_has_one_heading_with_everything_under_it() -> None:
    sections = [
        AnalysisSection(kind="detail", paragraphs=["Satu."], bullets=["a"]),
        AnalysisSection(kind="findings", bullets=["temuan"]),
        AnalysisSection(kind="detail", paragraphs=["Dua."], bullets=["b"]),
        AnalysisSection(kind="detail", paragraphs=["Tiga."]),
    ]
    markdown = sections_to_markdown(sections, "id")
    assert markdown.count("### Penjelasan Detail") == 1 and markdown.count("### Temuan Utama") == 1
    assert markdown.index("Satu.") < markdown.index("Dua.") < markdown.index("Tiga.") < markdown.index("### Temuan Utama")  # first-seen order of the kinds
    assert "- a\n- b" in markdown
