from __future__ import annotations

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
