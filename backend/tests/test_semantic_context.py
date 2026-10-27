import pytest

from app.semantic.context import SemanticContextService
from tests.test_history import contextualize_question


def test_context_is_derived_from_the_actual_tempo_ossie_contract() -> None:
    context = SemanticContextService()

    assert len(context.datasets) == 24
    assert len(context.metrics) == 72
    material = context.table_policy("gold.rpt_sap_material_month_semantic")
    assert "material" in material.columns
    assert "sell_in_bill_val" in material.columns
    assert material.domain == "material_360"


def test_context_compacts_only_approved_schema_without_credentials() -> None:
    context = SemanticContextService()

    payload = context.planner_context(["sales", "stock_tempo"])
    serialized = str(payload).lower()

    assert "gold.rpt_sap_material_month_semantic" in serialized
    assert "gold.corr_stock_tempo_month_seta" in serialized
    assert "password" not in serialized
    assert "api_key" not in serialized


def test_dataset_name_scopes_context_to_only_that_dataset() -> None:
    context = SemanticContextService()

    payload = context.planner_context(["monthly_executive"])

    assert [dataset["name"] for dataset in payload["datasets"]] == ["monthly_executive"]
    assert payload["metrics"]
    assert {metric["dataset"] for metric in payload["metrics"]} == {"monthly_executive"}


def test_top_products_gross_sales_uses_governed_material_metric() -> None:
    context = SemanticContextService()

    resolution = context.resolve("Bisa bantu cek berapa gross sales untuk top 5 produk?")
    sql = context.compile_governed(
        resolution["metric"],
        "Bisa bantu cek berapa gross sales untuk top 5 produk?",
        resolution.get("dimensions"),
    )

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "material_sell_in_value"
    assert resolution["dimensions"] == ["material"]
    assert "d.has_sell_in = TRUE" in sql
    assert "GROUP BY d.material" in sql
    assert "ORDER BY metric_value DESC" in sql
    assert "LIMIT 5" in sql


@pytest.mark.parametrize("reply", ["sell in", "penjualan tempo ke customer"])
def test_sell_in_clarification_keeps_top_product_grain(reply: str) -> None:
    history = [{
        "question": "Berapa total produk dengan penjualan terbanyak, kasih top 5 saja?",
        "answer": {"direct_answer": "Pilih Sell-In (penjualan Tempo ke customer) atau Sell-Out?"},
    }]

    contextualized = contextualize_question(reply, history, clarification_choice="sell-in")
    context = SemanticContextService()
    resolution = context.resolve(contextualized)
    sql = context.compile_governed(resolution["metric"], contextualized, resolution["dimensions"])

    assert resolution["metric"] == "material_sell_in_value"
    assert resolution["dimensions"] == ["material"]
    assert "LIMIT 5" in sql


def test_stock_guidance_uses_governed_metric_knowledge_and_examples() -> None:
    context = SemanticContextService()

    guidance = context.guidance_context("Saya mau tahu data stok bisa apa saja?")

    metric_names = {metric["name"] for metric in guidance["metrics"]}
    assert guidance["focus"] == "stock"
    assert "stock_tempo_total_qty" in metric_names
    assert "sat_store_stock_quantity" in metric_names
    assert any("stok" in example.casefold() or "stock" in example.casefold() for example in guidance["examples"])


def test_retail_stock_choice_resolves_without_repeating_clarification() -> None:
    resolution = SemanticContextService().resolve("stok retail")

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sat_store_stock_quantity"


@pytest.mark.parametrize("question", [
    "Stok di DC partner sekarang berapa ya per PLU?",
    "DC mana yang stoknya paling kecil bulan ini?",
    "DC partner",
    "DC partner mana paling rendah bulan ini?",
])
def test_explicit_partner_dc_stock_scope_does_not_repeat_clarification(question: str) -> None:
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sat_dc_stock_quantity"


def test_fastest_picking_orders_ascending_by_minutes() -> None:
    context = SemanticContextService()
    question = "Sales office mana picking-nya paling efisien (tercepat) Q4 2024?"
    resolution = context.resolve(question)
    sql = context.compile_governed(
        resolution["metric"],
        question,
        resolution.get("dimensions"),
    )
    assert resolution["metric"] == "average_picking_minutes"
    assert "ORDER BY metric_value ASC" in sql


def test_fastest_unloading_orders_ascending_by_minutes() -> None:
    context = SemanticContextService()
    question = "Sales office mana unloading-nya paling efisien (tercepat) Q4 2024?"
    resolution = context.resolve(question)
    sql = context.compile_governed(
        resolution["metric"],
        question,
        resolution.get("dimensions"),
    )
    assert resolution["metric"] == "average_unloading_minutes"
    assert "ORDER BY metric_value ASC" in sql


def test_named_dc_city_applies_dcname_predicate_in_sql() -> None:
    context = SemanticContextService()
    question = "Berapa stok SAT di DC Palembang Q4 2024?"
    resolution = context.resolve(question)
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))

    assert resolution["metric"] == "sat_dc_stock_quantity"
    assert "PALEMBANG" in sql.upper()


def test_po_do_gap_by_sales_office_resolves_office_grain() -> None:
    resolution = SemanticContextService().resolve(
        "Sales office mana dengan gap PO vs DO terbesar Q4 2024?"
    )
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_service_unfulfilled_quantity"
    assert resolution.get("dimensions") == ["sales_off"]


def test_current_partner_dc_stock_ranking_uses_latest_snapshot_and_top_ten() -> None:
    context = SemanticContextService()
    question = "DC mana yang stoknya paling kecil bulan ini?"
    resolution = context.resolve(question)
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))

    assert "d.dcname AS dcname" in sql
    assert "d.thn = 2024" in sql
    assert "d.bln = 'DEC'" in sql
    assert "ORDER BY metric_value ASC" in sql
    assert "LIMIT 10" in sql


def test_stock_rankings_are_capped_at_top_ten() -> None:
    context = SemanticContextService()

    default_sql = context.compile_governed(
        "sat_dc_stock_quantity",
        "PLU mana yang stok DC partner paling tinggi?",
    )
    oversized_sql = context.compile_governed(
        "sat_store_stock_quantity",
        "Tampilkan top 50 PLU dengan stok toko tertinggi",
    )

    assert "LIMIT 10" in default_sql
    assert "LIMIT 10" in oversized_sql


@pytest.mark.parametrize("question", [
    "Coba jumlahin total stok DC sama stok toko, jadi berapa total pipeline kita?",
    "Jumlahkan stock DC dengan stok di toko",
    "jumlah stok DC dan toko",
    "total persediaan DC partner dan toko",
    "gabungkan persediaan distribution center dan store",
])
def test_dc_and_toko_stock_cannot_be_added_as_total_pipeline(question: str) -> None:
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "needs_clarification"
    assert resolution["reason"] == "sat_idm_stock_level_aggregation"


@pytest.mark.parametrize("question", [
    "store mana yang stoknya paling rendah bulan ini?",
    "toko",
    "toko mana paling rendah bulan ini?",
])
def test_explicit_store_scope_resolves_without_repeating_clarification(question: str) -> None:
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sat_store_stock_quantity"


def test_what_else_question_marks_sales_as_excluded_instead_of_focus() -> None:
    guidance = SemanticContextService().guidance_context("Bisa bantu apa lagi selain data sales?")

    assert guidance["focus"] is None
    assert guidance["excluded_focus"] == "sales"
    assert guidance["metrics"] == []


def test_what_else_uses_session_last_metric_when_no_selain_phrase() -> None:
    guidance = SemanticContextService().guidance_context(
        "Kamu bisa apa lagi ya?",
        session_last_metric="sat_dc_stock_quantity",
        session_capability_hint={
            "last_metric": "sat_dc_stock_quantity",
            "last_question": "Top 10 DC penumpukan stok",
            "last_answer_excerpt": "DC X memimpin stok",
        },
    )

    assert guidance["excluded_focus"] == "stock_sat"
    assert guidance["session_capability_hint"]["last_question"].startswith("Top 10")
    lines = guidance["domain_capability_lines"]
    assert not any(line.startswith("Stock SAT") for line in lines)
    assert any(line.startswith("Sales / Sell-In") for line in lines)


def test_domain_capability_insight_lines_lists_all_governed_domains() -> None:
    ctx = SemanticContextService()
    lines = ctx.domain_capability_insight_lines()
    assert len(lines) == 9
    assert any(line.startswith("Sales / Sell-In") for line in lines)
    assert all("Contoh:" in line for line in lines)


def test_domain_capability_insight_lines_respects_excluded_focus() -> None:
    ctx = SemanticContextService()
    lines = ctx.domain_capability_insight_lines(exclude_focus="sales")
    assert len(lines) == 8
    assert not any(line.startswith("Sales / Sell-In") for line in lines)


def test_broad_guidance_offers_cross_domain_governed_examples() -> None:
    guidance = SemanticContextService().guidance_context("Halo, bisa bantu apa?")

    options = {option["name"]: option for option in guidance["domain_options"]}
    assert len(options) == 9
    assert len(guidance["domain_capability_lines"]) == 9
    assert options["Stock SAT (Alfamart)"]["metrics"] == [
        "sat_dc_stock_quantity",
        "sat_store_stock_quantity",
    ]
    assert options["Picking"]["examples"]
    assert options["SAT Promo"]["examples"]


def test_governed_compiler_uses_real_requested_dimensions() -> None:
    context = SemanticContextService()
    monthly = context.compile_governed("sat_dc_stock_quantity", "Berapa quantity DC Stock per bulan?")
    division = context.compile_governed("sat_store_stock_quantity", "Division mana dengan Store Stock tertinggi?")
    material = context.compile_governed("sat_oos_rate", "Material code mana dengan SAT OOS rate tertinggi?")

    assert "d.bln AS bln" in monthly
    assert "GROUP BY d.thn, d.bln" in monthly
    assert "d.division AS division" in division
    assert "GROUP BY d.division" in division
    assert "d.material_code AS material_code" in material
    assert "GROUP BY d.material_code" in material
    assert "LIMIT 10" in material
    assert "LIMIT 50" not in material


def test_company_wide_governed_metric_keeps_higher_default_limit() -> None:
    context = SemanticContextService()
    sql = context.compile_governed(
        "company_fill_rate",
        "Fill rate kita sekarang berapa secara keseluruhan?",
        [],
    )
    assert "GROUP BY" not in sql
    assert "LIMIT 50" in sql


def test_stock_tempo_to_sell_in_ratio_ranking_filters_zero_sell_in_and_nulls_last() -> None:
    context = SemanticContextService()
    sql = context.compile_governed(
        "stock_tempo_to_sell_in_ratio",
        "Produk mana dengan rasio stok Tempo terhadap penjualan sell-in paling tinggi?",
        ["material"],
    )
    assert "HAVING SUM(d.sell_in_bill_qty) > 0" in sql
    assert "ORDER BY metric_value DESC NULLS LAST" in sql


def test_stock_tempo_to_sell_in_ratio_zero_movement_skips_sell_in_having() -> None:
    context = SemanticContextService()
    sql = context.compile_governed(
        "stock_tempo_to_sell_in_ratio",
        "Material apa yang tidak laku sama sekali di Q4?",
        ["material"],
    )
    assert "SUM(d.sell_in_bill_qty) > 0" not in sql


@pytest.mark.parametrize("question", [
    "Produk mana dengan rasio stok Tempo terhadap penjualan sell-in paling tinggi?",
    "Produk mana dengan perbandingan stok Tempo dan sell-in paling tinggi?",
    "Branch mana dengan sell-out tinggi dibanding DC stock?",
    "PLU mana dengan store stock tinggi tetapi OOS juga tinggi?",
])
def test_multi_concept_paraphrase_cannot_use_a_partial_metric(question: str) -> None:
    resolution = SemanticContextService().resolve(question)

    if resolution["status"] == "resolved":
        assert any(token in resolution["metric"] for token in ("_to_", "_vs_"))
    else:
        assert resolution["status"] in {"fallback", "needs_clarification"}


@pytest.mark.parametrize(("question", "dimensions"), [
    ("Berapa persen toko yang kosong stoknya pas disurvei bulan lalu?", []),
    ("Material apa yang paling sering kosong di rak?", ["material_code"]),
    ("Customer/toko mana yang paling sering ngalamin stok kosong?", ["cust_id", "cust_code"]),
])
def test_natural_sat_oos_questions_route_to_oos_metric(question: str, dimensions: list[str]) -> None:
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sat_oos_rate"
    assert resolution["dimensions"] == dimensions


def test_natural_sat_oos_last_month_uses_latest_governed_month() -> None:
    context = SemanticContextService()
    question = "Berapa persen toko yang kosong stoknya pas disurvei bulan lalu?"
    resolution = context.resolve(question)

    sql = context.compile_governed(resolution["metric"], question, resolution["dimensions"])

    assert "d.calmonth_date = CAST('2024-12-01' AS DATE)" in sql


def test_oos_sales_causality_is_rejected_instead_of_redirected_to_sales() -> None:
    resolution = SemanticContextService().resolve(
        "OOS ini pengaruh ke penurunan sales berapa besar sih?"
    )

    assert resolution["status"] == "unsupported"
    assert resolution["reason"] == "oos_sales_causality_unavailable"


@pytest.mark.parametrize(("question", "metric", "dimensions"), [
    ("Fill rate kita sekarang berapa secara keseluruhan?", "company_fill_rate", []),
    ("Material apa yang fill rate-nya paling jelek?", "service_fill_rate", ["material"]),
    ("Sales office mana yang fill rate-nya paling rendah?", "sales_office_service_fill_rate", ["sales_off"]),
    ("Ada gap gak antara PO yang masuk sama DO yang kekirim?", "service_unfulfilled_quantity", []),
])
def test_service_level_uat_questions_use_published_metrics(
    question: str, metric: str, dimensions: list[str]
) -> None:
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == metric
    assert resolution.get("dimensions", []) == dimensions


def test_worst_material_fill_rate_includes_sell_in_for_runner_classification() -> None:
    context = SemanticContextService()
    question = (
        "Material apa yang fill rate-nya paling jelek, "
        "dan apakah itu produk high-runner atau long tail?"
    )
    resolution = context.resolve(question)
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))

    assert resolution["metric"] == "service_fill_rate"
    assert "sell_in_qty" in sql
    assert "HAVING SUM(d.service_po_qty) > 0" in sql
    assert "rpt_service_level_material_month_semantic" in sql


def test_stock_cover_question_filters_material_and_uses_full_q4() -> None:
    context = SemanticContextService()
    question = (
        "sekarang bisa bantu tampilkan gak produk/ material 500-21-02 di cabang 0201 "
        "dan hitung bisa meng-cover penjualan berapa hari dari stok tersebut"
    )
    resolution = context.resolve(question)
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))

    assert "d.material = '500-21-02'" in sql
    assert "d.calmonth BETWEEN 202410 AND 202412" in sql
    assert "ORDER BY metric_value DESC" not in sql
    assert "LIMIT 1" in sql


def test_polite_sekarang_prefix_does_not_force_december_only_snapshot() -> None:
    context = SemanticContextService()
    question = "sekarang bisa bantu tampilkan material 500-21-02 sell-in"
    sql = context.compile_governed("material_sell_in_value", question, ["material"])

    assert "d.calmonth BETWEEN 202410 AND 202412" in sql
    assert "d.calmonth = 202412" not in sql


def test_stok_sekarang_still_uses_latest_month_snapshot() -> None:
    context = SemanticContextService()
    question = "Stok di DC partner sekarang berapa ya per PLU?"
    resolution = context.resolve(question)
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))

    assert "d.thn = 2024" in sql
    assert "d.bln = 'DEC'" in sql


def test_two_office_material_compare_raises_row_limit() -> None:
    context = SemanticContextService()
    question = (
        "Q4 2024, bandingkan sales office Tempo (sell-in) 0201 vs 0212: "
        "tampilkan total nilai sell-in gross billing masing-masing cabang dan "
        "10 material/produk dengan kontribusi penjualan terbesar per cabang"
    )
    resolution = context.resolve(question)
    sql = context.compile_governed(
        resolution["metric"],
        question,
        resolution.get("dimensions"),
    )
    assert "d.sales_office IN ('0201', '0212')" in sql
    assert "LIMIT 20" in sql


def test_b2b_branch_code_in_question_adds_branch_filter() -> None:
    context = SemanticContextService()
    question = "nilai sell-out partner di cabang 0201"
    sql = context.compile_governed("b2b_branch_sell_out_value", question, None)

    assert "UPPER(d.branch) LIKE CONCAT('%', UPPER('0201'), '%')" in sql
    assert "LIMIT 1" in sql
    assert "ORDER BY metric_value DESC" not in sql


def test_b2b_branch_city_fragment_uses_like_predicate() -> None:
    context = SemanticContextService()
    question = "breakdown based on cabang palembang, top 3 produk terbaik based on penjualan"
    sql = context.compile_governed("b2b_branch_sell_out_value", question, ["branch"])

    assert "UPPER(d.branch) LIKE CONCAT('%', UPPER('palembang'), '%')" in sql
    assert "d.branch = 'palembang'" not in sql


def test_b2b_dc_ranking_question_still_uses_value_ranking() -> None:
    context = SemanticContextService()
    question = (
        "Top 10 DC Alfamart dengan penjualan tertinggi\n"
        "Klarifikasi pengguna: sell-out"
    )
    resolution = context.resolve(question)
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))

    assert "GROUP BY d.branch" in sql
    assert "ORDER BY metric_value DESC" in sql
    assert "LIMIT 10" in sql


def test_stock_cover_material_rank_orders_by_stock_value_and_filters_zero_sell_in() -> None:
    question = (
        "Ada concern cash tied in stock — bisa hitung months of stock cover Q4 2024? "
        "Kalau perlu filter material, ambil yang paling material secara nilai stok."
    )
    service = SemanticContextService()
    resolution = service.resolve(question)
    assert resolution["metric"] == "months_of_stock_cover"
    sql = service.compile_governed(resolution["metric"], question, resolution.get("dimensions"))
    assert "SUM(d.sell_in_bill_qty) > 0" in sql
    assert "ORDER BY SUM(d.warehouse_stock_val) DESC" in sql


def test_stock_cover_at_branch_sets_dimension_mismatch_not_sql_fallback() -> None:
    question = (
        "produk material 500-21-02 di cabang 0201 hitung bisa meng-cover "
        "penjualan berapa hari dari stok tersebut"
    )
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "months_of_stock_cover"
    assert resolution.get("dimension_mismatch") == ["branch"]


def test_dc_alfamart_sell_out_clarification_resolves_to_branch_ranking() -> None:
    context = SemanticContextService()
    question = (
        "Top 10 DC Alfamart dengan penjualan tertinggi\n"
        "Klarifikasi pengguna: sell-out"
    )
    resolution = context.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "b2b_branch_sell_out_value"
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))
    assert "gold.corr_b2b_branch_estore_month" in sql
    assert "GROUP BY d.branch" in sql
    assert "GROUP BY d.material" not in sql
    assert "LIMIT 10" in sql


@pytest.mark.parametrize("question", [
    "toko mana yang penjualannya paling tinggi",
    "outlet mana yang paling laris",
    "top 10 outlet alfamart",
    "toko dengan omset terbesar di alfamart",
    "e-store mana yang paling banyak penjualannya",
])
def test_outlet_toko_gerai_questions_resolve_to_b2b_branch_metric_without_sales_stage_clarification(
    question: str,
) -> None:
    context = SemanticContextService()
    resolution = context.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "b2b_branch_sell_out_value"
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))
    assert "GROUP BY d.e_store" in sql


def test_sell_in_sales_stage_clarification_is_unaffected_by_outlet_skip() -> None:
    resolution = SemanticContextService().resolve("berapa penjualan sell-in bulan ini")

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "gross_billing_value"


def test_existing_salesoffice_and_ratio_direction_skips_are_unaffected() -> None:
    context = SemanticContextService()

    salesoffice_resolution = context.resolve("sales office mana dengan penjualan tertinggi")
    assert salesoffice_resolution["status"] == "resolved"

    ratio_resolution = context.resolve("rasio penjualan partner terhadap penjualan tempo")
    assert ratio_resolution["status"] == "resolved"
    assert ratio_resolution["metric"] == "sell_out_to_sell_in_value_ratio"


@pytest.mark.parametrize("question", [
    "tren penjualan sell-in per bulan, naik atau turun",
    "tren stok tempo per bulan",
])
def test_pure_trend_questions_order_chronologically(question: str) -> None:
    context = SemanticContextService()
    resolution = context.resolve(question)

    assert resolution["status"] == "resolved"
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))
    assert "ORDER BY d.calmonth ASC" in sql


def test_ranking_with_bulan_keyword_still_orders_by_metric_value() -> None:
    context = SemanticContextService()
    resolution = context.resolve("top 10 produk bulan ini")

    assert resolution["status"] == "resolved"
    sql = context.compile_governed(
        resolution["metric"], "top 10 produk bulan ini", resolution.get("dimensions")
    )
    assert "ORDER BY metric_value DESC" in sql


@pytest.mark.parametrize("question", [
    "tren fill rate per bulan",
    "tren SAT OOS per bulan",
    "tren stok cover per bulan",
])
def test_trend_questions_group_by_time_even_for_shortcut_metrics_with_empty_dimensions(
    question: str,
) -> None:
    context = SemanticContextService()
    resolution = context.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution.get("dimensions") == []
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))
    assert "GROUP BY" in sql
    assert "ASC" in sql


def test_shortcut_metric_without_trend_keyword_stays_dimensionless() -> None:
    resolution = SemanticContextService().resolve("fill rate kita sekarang berapa secara keseluruhan")

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "company_fill_rate"
    assert resolution.get("dimensions") == []


def test_zero_movement_product_question_adds_having_clause() -> None:
    context = SemanticContextService()
    resolution = context.resolve("produk mana yang tidak laku sama sekali")

    assert resolution["status"] == "resolved"
    sql = context.compile_governed(
        resolution["metric"], "produk mana yang tidak laku sama sekali", resolution.get("dimensions")
    )
    assert "HAVING" in sql
    assert "= 0" in sql


@pytest.mark.parametrize("question", [
    "produk paling laku",
    "produk terlaris",
])
def test_best_selling_product_questions_do_not_trigger_having_clause(question: str) -> None:
    context = SemanticContextService()
    resolution = context.resolve(question)

    assert resolution["status"] == "resolved"
    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))
    assert "HAVING" not in sql


@pytest.mark.parametrize("question", [
    "toko mana yang paling sering OOS",
    "outlet mana yang paling sering kehabisan stok",
    "gerai dengan OOS tertinggi",
])
def test_oos_questions_with_store_ranking_language_break_down_by_store(question: str) -> None:
    context = SemanticContextService()
    resolution = context.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sat_oos_rate"
    assert resolution.get("dimensions") == ["cust_id", "cust_code"]


def test_aggregate_oos_question_about_percent_of_stores_stays_dimensionless() -> None:
    resolution = SemanticContextService().resolve(
        "Berapa persen toko yang kosong stoknya pas disurvei bulan lalu?"
    )

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sat_oos_rate"
    assert resolution.get("dimensions") == []


def test_top_products_at_tempo_resolves_sell_in_via_domain_graph() -> None:
    resolution = SemanticContextService().resolve("Top 10 produk dengan penjualan terbesar di Tempo")
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "material_sell_in_value"


@pytest.mark.parametrize("question", [
    "penjualan terbesar di Tempo",
    "berapa penjualan di Tempo bulan ini",
])
def test_sales_questions_mentioning_tempo_as_a_location_still_ask_sales_stage(question: str) -> None:
    # Generic "penjualan di Tempo" without product/top ranking stays ambiguous
    # (General Trade/Sell-In vs B2B/Sell-Out). B3 Q01 is explicit Top-N produk
    # and resolves via domain graph governed_intents instead.
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "needs_clarification"
    assert resolution["reason"] == "sales_stage"


@pytest.mark.parametrize("question", [
    "Top 10 cabang/ sales office dengan penjualan terbesar di tempo",
    "Sales office mana dengan picking delay rate tertinggi?",
    "Cabang mana dengan rata-rata unloading terlama Q4?",
])
def test_cabang_dimension_hint_does_not_produce_a_false_dimension_mismatch(question: str) -> None:
    # "cabang" ambiguously hints branch/sales_off/sales_office at once.
    # Once the winning metric's allowed_dimensions actually covers one
    # reading of "cabang" (e.g. sales_office), the other readings must not
    # be reported as an unmet dimension_mismatch - that used to force every
    # one of these questions through the LLM SQL-fallback planner instead
    # of the already-correct governed SQL, and could fail outright.
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution.get("dimension_mismatch") == []


def test_promo_uplift_ranking_defaults_to_top_ten() -> None:
    context = SemanticContextService()
    question = "coba saya pengen liat margin uplift"
    resolution = context.resolve("margin uplift")
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "promo_material_margin_uplift"

    sql = context.compile_governed(resolution["metric"], question, resolution.get("dimensions"))
    assert "d.material AS material" in sql
    assert "ORDER BY metric_value DESC" in sql
    assert "LIMIT 10" in sql
    assert "LIMIT 50" not in sql


def test_promo_b2b_sellout_uplift_resolves_without_gt_clarification() -> None:
    resolution = SemanticContextService().resolve(
        "Uplift sell-out Alfamart untuk material SAT Promo Nov vs Des 2024"
    )
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "promo_b2b_sellout_revenue_uplift"


def test_promo_program_status_distribution_resolves_observation_count() -> None:
    resolution = SemanticContextService().resolve(
        "Distribusi promo SAT by program status Q4 2024"
    )
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "promo_observation_count"
    assert resolution.get("matched_alias") == "promo_program_status_distribution"


def test_material_sell_in_quantity_ranking_route() -> None:
    resolution = SemanticContextService().resolve(
        "Produk mana yang paling banyak terjual (quantity sell-in) di Tempo Q4 2024? Top 10"
    )
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "material_sell_in_quantity"


def test_promo_roi_with_operational_recommendation_stays_clarification() -> None:
    resolution = SemanticContextService().resolve(
        "Hitung promo dengan ROI terbaik dan berikan rekomendasi operasional"
    )
    assert resolution["status"] == "needs_clarification"
    assert resolution.get("reason") == "promo_roi_proxy_choice"


def test_promo_uplift_honours_explicit_top_five() -> None:
    context = SemanticContextService()
    resolution = context.resolve("top 5 revenue uplift promo")
    sql = context.compile_governed(
        resolution["metric"],
        "top 5 revenue uplift promo",
        resolution.get("dimensions"),
    )
    assert "LIMIT 5" in sql


def test_promo_roi_proxy_clarification_answer_in_prose_resolves_revenue_uplift() -> None:
    answer = (
        "oke sekali lagi coba keluarkan penjualan General Trade (bukan Alfamart langsung) "
        "untuk material yang sama, dibandingkan November (baseline) vs Desember (bulan promo)"
    )
    resolution = SemanticContextService().resolve(answer)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "promo_material_revenue_uplift"


@pytest.mark.parametrize("choice", ["Revenue Uplift", "revenue uplift"])
def test_promo_roi_proxy_short_label_still_resolves(choice: str) -> None:
    resolution = SemanticContextService().resolve(choice)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "promo_material_revenue_uplift"


def test_uat_branch_service_level_ranking_resolves_sales_office_fill_rate() -> None:
    question = "Hitung service level/ fill rate di cabang tempo dan urutkan SL terjelek"
    service = SemanticContextService()
    resolution = service.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_service_fill_rate"
    assert resolution.get("dimensions") == ["sales_off"]
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "gold.corr_service_sales_office_material_month" in sql
    assert "GROUP BY d.sales_off" in sql
    assert "ORDER BY metric_value ASC" in sql
    assert "LIMIT 10" in sql


def test_tingkat_layanan_wording_resolves_sales_office_service_level() -> None:
    question = "Sales office mana dengan tingkat layanan terendah Q4 2024? Top 10"
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_service_fill_rate"


@pytest.mark.parametrize("question", [
    "Service level / fill rate cabang Tempo terbaik?",
    "Hitung service level fill rate per sales office dan urutkan terbaik",
    "Sales office mana dengan service level terendah Q4 2024? Top 10",
])
def test_other_branch_service_level_rankings_remain_governed(question: str) -> None:
    resolution = SemanticContextService().resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_service_fill_rate"


def test_tingkat_pemenuhan_cabang_resolves_office_fill_rate() -> None:
    question = "Cabang Tempo mana dengan tingkat pemenuhan terendah November 2024?"
    service = SemanticContextService()
    resolution = service.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_service_fill_rate"
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "d.calmonth = 202411" in sql


def test_otif_routes_to_office_fill_rate_proxy() -> None:
    resolution = SemanticContextService().resolve(
        "Bagaimana OTIF per sales office Q4 2024? Urutkan terburuk top 10"
    )
    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sales_office_service_fill_rate"
    assert resolution.get("matched_alias") == "otif_proxy_fill_rate"


def test_bill_to_po_ratio_resolves_material_fill_rate_proxy() -> None:
    question = "Rasio bill-to-PO per material Desember 2024, terendah top 10"
    service = SemanticContextService()
    resolution = service.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "material_fill_rate"
    assert resolution.get("matched_alias") == "bill_to_po_fill_rate_proxy"
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "d.calmonth = 202412" in sql
    assert "service_do_qty" in sql and "service_po_qty" in sql
    assert "HAVING" in sql and "< 1" in sql
    assert "ORDER BY metric_value ASC" in sql


def test_dc_penumpukan_stok_not_material_sell_in_billing() -> None:
    question = (
        "Tampilkan 10 DC dengan penumpukan stok produk yang tertinggi, "
        "lalu analisa apakah ada yang bisa kita lakukan untuk memperbaiki situasi tersebut"
    )
    resolution = SemanticContextService().resolve(question)
    assert resolution["status"] == "resolved"
    assert resolution["metric"] in ("sat_dc_stock_quantity", "sat_dc_stock_value")
    assert resolution["dimensions"] == ["dcname"]
    assert resolution["metric"] != "material_sell_in_value"
    sql = SemanticContextService().compile_governed(
        resolution["metric"], question, resolution["dimensions"]
    )
    assert "rpt_sat_dc_month" in sql
    assert "dcname" in sql.lower()


def test_bill_to_po_with_penagihan_process_advice_stays_fill_rate_not_billing() -> None:
    question = (
        "Tampilkan 10 material dengan rasio bill-to-PO terendah di Desember 2024 "
        "dan analisa penyebab potensial beserta saran perbaikan proses penagihan."
    )
    service = SemanticContextService()
    resolution = service.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "material_fill_rate"
    assert resolution.get("matched_alias") == "bill_to_po_fill_rate_proxy"
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "rpt_sap_material_month_semantic" in sql
    assert "sales_office_material" not in sql
    assert "sell_in_bill_val" not in sql


def test_bill_to_po_positive_ratio_having_and_limit_ten_material() -> None:
    question = (
        "tampilkan 10 material dengan rasio bill-to-PO terendah di Desember 2024, "
        "hanya tampilkan produk dengan nilai rasio positif, dan analisa penyebab potensial "
        "beserta saran perbaikan proses penagihan."
    )
    service = SemanticContextService()
    resolution = service.resolve(question)
    assert resolution["metric"] == "material_fill_rate"
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "LIMIT 10" in sql
    assert "> 0" in sql
    assert "sell_in_bill_val" not in sql


def test_bill_to_po_and_nilai_penagihan_still_prompts_clarification() -> None:
    from app.semantic.domain_graph import try_clarification_intent

    question = "Bandingkan bill-to-PO dan nilai penagihan grosir per material Desember 2024"
    assert try_clarification_intent(question) is not None
    resolution = SemanticContextService().resolve(question)
    assert resolution["status"] == "needs_clarification"


def test_november_penagihan_material_uses_single_month_filter() -> None:
    question = "Nilai penagihan grosir per material November 2024 top 10 kontribusi"
    service = SemanticContextService()
    resolution = service.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "material_sell_in_value"
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "d.calmonth = 202411" in sql


def test_sat_store_stock_october_resolves() -> None:
    question = "Rata-rata stok toko Alfamart Oktober 2024 per divisi"
    service = SemanticContextService()
    resolution = service.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "sat_store_stock_quantity"
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "d.thn = 2024" in sql and "d.bln = 'OCT'" in sql


def test_days_of_supply_routes_months_of_stock_cover() -> None:
    question = "Material dengan hari persediaan terpanjang November 2024 top 10"
    service = SemanticContextService()
    resolution = service.resolve(question)

    assert resolution["status"] == "resolved"
    assert resolution["metric"] == "months_of_stock_cover"
    sql = service.compile_governed(resolution["metric"], question, resolution["dimensions"])
    assert "d.calmonth = 202411" in sql
