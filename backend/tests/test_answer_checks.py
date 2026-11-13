from __future__ import annotations

import pytest

from app.ask_data.answer_checks import review_answer, strip_calculation_label, unverified_figures
from app.core.models import AnalysisOutput

MONTHS = [{"month": f"2026-0{i + 1}", "metric_value": v} for i, v in enumerate([1014, 904, 1002, 963, 969, 1074, 1035, 1039])]


def _answer(direct: str, summary: str = "", insights: list[str] | None = None) -> AnalysisOutput:
    return AnalysisOutput(direct_answer=direct, executive_summary=summary, insights=insights or [], business_implications=[], caveats=[], data_reference="t")


def test_a_wrong_average_is_caught_and_a_right_one_is_not() -> None:
    assert unverified_figures(["Between January and August we received 904 to 1,074 orders, an average of 998."], MONTHS) == ["998"]
    assert unverified_figures(["An average of 1,000 orders, 8,000 in total."], MONTHS) == []  # mean 1000 and sum 8000 are derivable


def test_figures_in_either_number_format_and_rounding_are_matched() -> None:
    rows = [{"region": "Kalimantan Timur", "metric_value": 23.1534}, {"region": "Jawa Timur", "metric_value": 16.3402}]
    assert unverified_figures(["Kalimantan Timur is at 23.15%, Jawa Timur 16,34%, a gap of 6.81 points."], rows) == []
    assert unverified_figures(["Kalimantan Timur is at 25.15%."], rows) == ["25.15"]
    assert unverified_figures(["There were 1.002 orders."], [{"metric_value": 1002}]) == []  # 1.002 as an Indonesian thousand


def test_small_counts_years_and_numbers_from_the_question_are_not_second_guessed() -> None:
    assert unverified_figures(["Top 5 of 8 regions in Q4 2024, up 40% overall."], MONTHS) == []
    assert unverified_figures(["The 15% threshold is exceeded."], [{"metric_value": 23.15}], "Is it above the 15% threshold?") == []


def test_the_calculation_label_the_app_already_shows_is_removed() -> None:
    assert strip_calculation_label("How this was calculated: The total_orders metric was counted. Ask for a breakdown next.") == "Ask for a breakdown next."
    assert strip_calculation_label("Cara penghitungan: Metrik total_orders dihitung per bulan.") == ""
    assert strip_calculation_label("Orders were stable across the period.") == "Orders were stable across the period."


def test_review_answer_cleans_the_text_and_warns_in_the_language_of_the_question() -> None:
    answer = _answer("An average of 998 orders a month.", "How this was calculated: counted by month.", ["How this was calculated: x", "Peak was in June."])
    cleaned, warnings = review_answer(answer, rows=MONTHS, question="how many orders per month", language="en")
    assert cleaned.executive_summary == "" and cleaned.insights == ["Peak was in June."]
    assert warnings and "998" in warnings[0] and warnings[0] in cleaned.caveats
    _, id_warnings = review_answer(answer, rows=MONTHS, question="berapa order per bulan", language="id")
    assert id_warnings[0].startswith("Angka 998")


def test_the_overall_value_and_what_follows_from_it_may_be_quoted() -> None:
    rows = [{"region": "Kalimantan Timur", "metric_value": 22.64}, {"region": "Bali", "metric_value": 18.34}, {"region": "Jawa Timur", "metric_value": 14.79}]
    text = ["Rata-rata keseluruhan 17,04%, Kalimantan Timur lebih tinggi 5,60 poin."]
    assert unverified_figures(text, rows, "churn per wilayah") == ["17,04", "5,60"]
    assert unverified_figures(text, rows, "churn per wilayah", [17.04]) == []


def test_a_figure_spoken_in_billions_or_as_a_ratio_is_derivable() -> None:
    rows = [{"channel": "App", "revenue": 19753449000}, {"channel": "Website", "revenue": 13042320000}]
    assert unverified_figures(["App menghasilkan 19,75 miliar, hampir 1,5 kali lipat dari Website."], rows) == []
    assert unverified_figures(["App menghasilkan 25,50 miliar."], rows) == ["25,50"]


def test_comparisons_are_worked_out_by_code_for_the_answer_to_quote() -> None:
    from app.ask_data.answer_checks import computed_figures, is_additive

    rows = [{"provinsi": "Jawa Tengah", "metric_value": 714496}, {"provinsi": "Jawa Timur", "metric_value": 574904}, {"provinsi": "Jawa Barat", "metric_value": 447832}]
    out = computed_figures(rows, 4996168, additive=True)
    assert out["highest"]["group"] == "Jawa Tengah" and out["ratio_highest_to_second"]["ratio"] == pytest.approx(1.2428, abs=1e-4)
    assert out["ratio_highest_to_lowest"] == pytest.approx(1.5955, abs=1e-4)
    assert out["these_rows_share_of_overall_pct"] == pytest.approx(34.77, abs=0.01)
    rates = computed_figures([{"regional": "Papua Maluku", "metric_value": 34.54}, {"regional": "Jatimbalinus", "metric_value": 11.4}], 16.07)
    assert "share_of_overall_pct" not in rates and rates["difference_from_overall"][0]["difference"] == pytest.approx(18.47, abs=1e-6)
    assert is_additive({"expression": "SUM(volume_kl)"}) and not is_additive({"expression": "COUNT(CASE WHEN x THEN 1 END) * 100.0 / COUNT(id)"})


def test_what_several_rows_together_are_of_the_whole_is_derivable() -> None:
    rows = [{"p": "A", "metric_value": 714496}, {"p": "B", "metric_value": 574904}, {"p": "C", "metric_value": 447832}]
    assert unverified_figures(["Ketiganya sekitar 34,8% dari total."], rows, "", [4996168]) == []
    assert unverified_figures(["A sekitar 1,26 kali B."], rows, "", [4996168]) == ["1,26"]  # 1,24 is right; the check still catches it


def test_every_group_is_placed_above_or_below_the_overall_value_so_only_and_both_are_counted_not_guessed() -> None:
    from app.ask_data.answer_checks import computed_figures

    # The rates by regional of the fuel sample: an answer said Jatimbalinus was the only one below 16.07, but five are.
    regional = {"Papua Maluku": 34.54, "Kalimantan": 29.66, "Sulawesi": 19.45, "Sumbagut": 15.69, "Sumbagsel": 13.88, "Jawa Bagian Barat": 13.18, "Jawa Bagian Tengah": 11.84, "Jatimbalinus": 11.4}
    out = computed_figures([{"regional": k, "metric_value": v} for k, v in regional.items()], 16.07)
    assert out["above_overall"] == {"count": 3, "of": 8, "groups": ["Papua Maluku", "Kalimantan", "Sulawesi"]}
    assert out["below_overall"]["count"] == 5 and "Sumbagut" in out["below_overall"]["groups"]
    assert len(out["difference_from_overall"]) == 8  # every group, not only the extremes
    # and by customer type: an answer said DODO and CODO were both above, but CODO is below
    types = computed_figures([{"tipe": "SPBU_DODO", "metric_value": 19.53}, {"tipe": "SPBU_CODO", "metric_value": 14.95}, {"tipe": "SPBU_COCO", "metric_value": 9.22}], 16.07)
    assert types["above_overall"]["groups"] == ["SPBU_DODO"] and types["below_overall"]["groups"] == ["SPBU_CODO", "SPBU_COCO"]


def test_a_follow_up_in_a_stray_script_is_left_out_and_the_fuller_analysis_is_checked_like_the_rest() -> None:
    from app.core.models import AnalysisOutput
    from app.ask_data.answer_checks import review_answer

    out = AnalysisOutput(
        direct_answer="Papua Maluku 34,54%.", executive_summary="", insights=[], business_implications=[], caveats=[], data_reference="",
        follow_up_questions=["Bagaimana rata-rata durasi di Papua Maluku dibandingkan dengan Kalimantan dalam c\u00f9ng periode?", "Tingkat Keterlambatan per bulan"],
        detailed_analysis="### Cara membacanya\n\nTiga dari delapan regional di atas 16,07%, dengan selisih 98,76 poin.",
    )
    assert out.follow_up_questions == ["Tingkat Keterlambatan per bulan"]  # "cùng" is not Indonesian
    rows = [{"regional": "Papua Maluku", "metric_value": 34.54}, {"regional": "Jatimbalinus", "metric_value": 11.4}]
    reviewed, warnings = review_answer(out, rows=rows, question="regional mana paling terlambat", language="id", extra_figures=[16.07])
    assert any("98,76" in w or "98.76" in w for w in warnings)  # a figure in the fuller analysis that is in no result
    assert reviewed.detailed_analysis.startswith("### Cara membacanya")
