import pytest

from app.core.models import AnalysisOutput
from app.services.conversational import TurnUnderstanding
from app.services.question_contextualize import apply_turn_understanding


def _llm_apply(raw: str, history: list, **fields) -> str:
    understanding = TurnUnderstanding(
        is_conversational=False,
        attach_domain_catalog=False,
        pipeline_question=fields.get("pipeline_question", raw),
        clarification_choice=fields.get("clarification_choice", ""),
        referential_follow_up=fields.get("referential_follow_up", False),
    )
    return apply_turn_understanding(raw, history, understanding)


def contextualize_question(raw: str, history: list, **fields) -> str:
    """Simulate LLM turn understanding in unit tests."""
    return _llm_apply(raw, history, **fields)
from app.services.history import ConversationStore


def test_history_persists_provider_model_and_structured_answer(tmp_path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite")
    answer = AnalysisOutput(
        direct_answer="10",
        executive_summary="Total is 10",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="query result",
        chart_spec=None,
    )

    store.append(
        "session-1",
        "question",
        answer,
        [{"value": 10}],
        None,
        "gemini",
        "gemini-model",
        status="SUCCESS",
        strategy="governed",
    )

    history = store.load("session-1")
    assert history[0]["provider"] == "gemini"
    assert history[0]["model"] == "gemini-model"
    assert history[0]["status"] == "SUCCESS"
    assert history[0]["strategy"] == "governed"
    assert history[0]["answer"]["direct_answer"] == "10"
    assert "reasoning" not in str(history).lower()


def test_delete_session_removes_all_turns(tmp_path) -> None:
    store = ConversationStore(tmp_path / "history.sqlite")
    answer = AnalysisOutput(
        direct_answer="ok",
        executive_summary="ok",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="x",
        chart_spec=None,
    )
    store.append("sess-a", "q1", answer, [], None, "gemini", "m", status="SUCCESS", strategy="governed")
    store.append("sess-a", "q2", answer, [], None, "gemini", "m", status="SUCCESS", strategy="governed")
    store.append("sess-b", "q3", answer, [], None, "gemini", "m", status="SUCCESS", strategy="governed")
    assert store.delete_session("sess-a") == 2
    assert store.load("sess-a") == []
    assert len(store.load("sess-b")) == 1


def test_history_persists_session_frame(tmp_path) -> None:
    from app.services.session_context import build_session_frame

    store = ConversationStore(tmp_path / "history.sqlite")
    frame = build_session_frame(
        question="top 5 cabang",
        status="SUCCESS",
        strategy="governed",
        rows=[{"sales_office": "0201", "metric_value": 1}, {"sales_office": "0212", "metric_value": 2}],
        metric="sales_office_sell_in_value",
        dimensions=["sales_office"],
    )
    answer = AnalysisOutput(
        direct_answer="ok",
        executive_summary="ok",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="x",
        chart_spec=None,
    )
    store.append(
        "s1",
        "top 5 cabang",
        answer,
        [{"sales_office": "0201"}],
        None,
        "gemini",
        "gemini-model",
        status="SUCCESS",
        strategy="governed",
        session_frame=frame,
    )
    loaded = store.load("s1")[0]
    assert loaded["session_frame"]["last_metric"] == "sales_office_sell_in_value"
    assert len(loaded["session_frame"]["ranked_entities"]) == 2
    assert loaded["model"] == "gemini-model"


def test_analytic_follow_up_question_is_not_merged_after_success_turn() -> None:
    history = [
        {
            "question": "Analisa data unloading dan picking dan berikan Analisa dan perbandingan dengan Industri standard",
            "answer": {
                "direct_answer": (
                    "Analisis unloading/picking Q4. Apakah Anda ingin detail per sales office?"
                ),
            },
        }
    ]
    reply = "Top 10 produk dengan penjualan terbesar di Tempo"
    assert contextualize_question(reply, history) == reply


def test_short_sell_in_follow_up_reuses_the_previous_question() -> None:
    history = [
        {
            "question": "Kalau jumlah penjualan selama Q4 berapa besar?",
            "answer": {"direct_answer": "Mau Sell-In atau Sell-Out?"},
        }
    ]

    contextualized = contextualize_question("untuk data sell-in ya", history, clarification_choice="sell-in")

    assert "Kalau jumlah penjualan selama Q4 berapa besar?" in contextualized
    assert "sell-in" in contextualized.casefold()


@pytest.mark.parametrize("reply", ["data sellout", "data sell out", "Sell-Out", "sell-out aja"])
def test_sell_out_clarification_replies_all_merge_with_the_prior_question(reply: str) -> None:
    history = [
        {
            "question": "Top 10 DC Alfamart dengan penjualan tertinggi",
            "answer": {
                "direct_answer": (
                    "Apakah Anda ingin melihat Sell-In (penjualan Tempo ke customer) "
                    "atau Sell-Out (penjualan partner ke konsumen akhir)?"
                ),
            },
        }
    ]

    contextualized = contextualize_question(reply, history, clarification_choice="sell-out")

    assert contextualized == (
        "Top 10 DC Alfamart dengan penjualan tertinggi\n"
        "Klarifikasi pengguna: sell-out"
    )


def test_plain_sell_in_choice_preserves_the_original_top_product_request() -> None:
    history = [
        {
            "question": "Berapa total produk dengan penjualan terbanyak, kasih top 5 saja?",
            "answer": {
                "direct_answer": "Apakah Anda ingin melihat Sell-In (penjualan Tempo ke customer) atau Sell-Out?",
            },
        }
    ]

    contextualized = contextualize_question("sell in", history, clarification_choice="sell-in")

    assert contextualized == (
        "Berapa total produk dengan penjualan terbanyak, kasih top 5 saja?\n"
        "Klarifikasi pengguna: sell-in"
    )


def test_descriptive_sell_in_choice_does_not_add_customer_as_a_dimension() -> None:
    history = [
        {
            "question": "Berapa total produk dengan penjualan terbanyak, kasih top 5 saja?",
            "answer": {
                "direct_answer": "Apakah Anda ingin melihat Sell-In (penjualan Tempo ke customer) atau Sell-Out?",
            },
        }
    ]

    contextualized = contextualize_question(
        "penjualan tempo ke customer", history, clarification_choice="sell-in"
    )

    assert contextualized.endswith("Klarifikasi pengguna: sell-in")
    assert "customer" not in contextualized.casefold()


def test_standalone_question_is_not_rewritten_from_history() -> None:
    history = [{"question": "Berapa total penjualan?", "answer": {"direct_answer": "Sell-In atau Sell-Out?"}}]

    assert contextualize_question("Top 5 produk dengan gross sales terbesar", history) == "Top 5 produk dengan gross sales terbesar"


def test_service_level_worst_branch_follow_up_rewrites_to_material_drilldown() -> None:
    history = [
        {
            "question": "Hitung service level/ fill rate di cabang tempo dan urutkan SL terjelek?",
            "answer": {
                "direct_answer": "Cabang dengan fill rate terendah adalah 0245 (41,36%).",
                "executive_summary": "",
                "insights": [],
            },
        }
    ]
    follow_up = "coba bantu analisa cabang paling jelek itu untuk yang top 1 ya kenapa dia bisa jelek ?"

    rewrite = (
        "Untuk sales office 0245 (cabang Tempo) pada Q4 2024, "
        "tampilkan 10 material dengan fill rate / service level terendah "
        f"Pertanyaan asli pengguna: {follow_up}"
    )
    contextualized = contextualize_question(follow_up, history, pipeline_question=rewrite)

    assert "sales office 0245" in contextualized
    assert "material" in contextualized.casefold()
    assert follow_up in contextualized


def test_unrelated_new_question_after_roi_promo_clarification_is_not_rewritten() -> None:
    # The ROI-promo proxy clarification is a long paragraph that happens to
    # share common domain words ("penjualan", "Tempo") with almost any new
    # question - a brand-new, unrelated topic must not be misread as the
    # user answering the ROI clarification just because of that overlap.
    history = [
        {
            "question": "Hitung promo dengan ROI terbaik dan berikan rekomendasi/ saran",
            "answer": {
                "direct_answer": (
                    "TEMPO tidak memiliki data biaya promo atau ROI langsung untuk SAT Promo "
                    "(Alfamart) - data yang tersedia hanya deskripsi mekanisme promo (teks bebas), "
                    "bukan nilai biaya terstruktur, dan SAT Promo hanya mencakup Desember 2024 tanpa "
                    "baseline bulan sebelumnya di channel yang sama. Satu-satunya proxy yang bisa "
                    "dihitung adalah dampak penjualan General Trade (bukan Alfamart langsung) untuk "
                    "material yang sama, dibandingkan November (baseline) vs Desember (bulan promo). "
                    "Metrik mana yang Anda mau?"
                ),
                "executive_summary": "",
                "insights": [],
            },
        }
    ]

    reply = "Top 10 produk dengan penjualan terbesar di Tempo"
    assert contextualize_question(reply, history) == reply


def test_unrelated_new_question_after_sales_stage_clarification_is_not_rewritten() -> None:
    history = [
        {
            "question": "berapa penjualan bulan ini?",
            "answer": {
                "direct_answer": (
                    "Apakah Anda ingin melihat Sell-In (penjualan Tempo ke customer) atau "
                    "Sell-Out (penjualan partner ke konsumen akhir)?"
                ),
            },
        }
    ]

    reply = "stok gudang tempo berapa banyak"
    assert contextualize_question(reply, history) == reply


def test_short_answer_to_stock_clarification_reuses_previous_question() -> None:
    history = [
        {
            "question": "Mau tahu tentang data stok, bisa analisis apa saja?",
            "answer": {"direct_answer": "Mau stok gudang Tempo, stok DC partner, atau stok retail?"},
        }
    ]

    prev = history[0]["question"]
    merged = f"{prev}\nKlarifikasi pengguna: stok retail"
    contextualized = contextualize_question("stok retail", history, pipeline_question=merged)

    assert "Mau tahu tentang data stok" in contextualized
    assert "Klarifikasi pengguna: stok retail" in contextualized


def test_domain_choice_can_be_found_in_executive_summary() -> None:
    history = [
        {
            "question": "Data stok bisa dipakai untuk analisis apa?",
            "answer": {
                "direct_answer": "Ada beberapa arah analisis stok yang tersedia.",
                "executive_summary": "Pilih stok gudang Tempo, DC partner, atau retail store.",
                "insights": ["Contoh: stok retail per division."],
            },
        }
    ]

    prev = history[0]["question"]
    merged = f"{prev}\nKlarifikasi pengguna: stok retail"
    contextualized = contextualize_question("stok retail", history, pipeline_question=merged)

    assert contextualized.endswith("Klarifikasi pengguna: stok retail")
