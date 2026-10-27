from app.services.conversational import TurnUnderstanding
from app.services.follow_up import (
    analysis_context_from_history,
    build_analysis_context,
    plan_follow_up,
    try_follow_up_governed_resolution,
    try_rewrite_follow_up_question,
)


def _understanding_for_question(question: str, ctx: dict) -> TurnUnderstanding | None:
    plan = plan_follow_up(question, ctx)
    if plan is None:
        return None
    entity = plan.filter_entity or {}
    return TurnUnderstanding(
        is_conversational=False,
        attach_domain_catalog=False,
        pipeline_question=question.strip(),
        referential_follow_up=True,
        follow_up_entity_id=str(entity.get("id") or "") or None,
        follow_up_entity_dimension=str(entity.get("entity_type") or entity.get("dimension") or "") or None,
        follow_up_rank=int(entity["rank"]) if isinstance(entity.get("rank"), int) else None,
        follow_up_material_drill=plan.to_grain == "material",
        follow_up_top_n=plan.limit,
    )
from app.services.session_context import build_session_frame


def test_build_analysis_context_from_b2b_ranking() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[
            {"rank": 1, "dimension": "branch", "id": "DC Palembang", "metric_value": 1e10},
            {"rank": 2, "dimension": "branch", "id": "DC Makassar", "metric_value": 9e9},
        ],
        last_question="top 5 dc penjualan b2b",
    )
    assert ctx["domain_id"] == "b2b"
    assert ctx["active_grain"] == "branch"
    assert len(ctx["result_catalog"]) == 2


def test_plan_follow_up_binds_palembang_and_drill_material() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[{"rank": 1, "dimension": "branch", "id": "DC Palembang", "metric_value": 1}],
        last_question="top 5 dc",
    )
    q = "breakdown based on cabang palembang, top 3 produk terbaik based on penjualan"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.to_grain == "material"
    assert plan.limit == 3
    assert plan.filter_entity is not None
    assert "Palembang" in str(plan.filter_entity["id"])


def test_plan_follow_up_top_material_monthly_sell_in() -> None:
    ctx = build_analysis_context(
        metric="material_sell_in_value",
        dimensions=["material"],
        entity_dimension="material",
        ranked_entities=[
            {"rank": 1, "dimension": "material", "id": "001-00-03", "metric_value": 289e9},
            {"rank": 2, "dimension": "material", "id": "073-09-03", "metric_value": 100e9},
        ],
        last_question="pareto penjualan desember 2024",
    )
    q = "coba untuk material paling tinggi itu kamu keluarkan jumlah penjualan perbulannya"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.to_grain is None
    assert plan.dimensions_override == ["calmonth"]
    assert plan.filter_entity is not None
    assert plan.filter_entity["id"] == "001-00-03"
    u = _understanding_for_question(q, ctx)
    res = try_follow_up_governed_resolution(q, ctx, u)
    assert res is not None
    assert res["metric"] == "material_sell_in_value"
    assert res["dimensions"] == ["calmonth"]
    assert any("001-00-03" in p for p in res["follow_up_entity_filters"])


def test_plan_follow_up_top_branch_monthly_sell_out() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[
            {"rank": 1, "dimension": "branch", "id": "DC Palembang", "metric_value": 1e10},
            {"rank": 2, "dimension": "branch", "id": "DC Makassar", "metric_value": 9e9},
        ],
        last_question="top 5 dc penjualan b2b Q4",
    )
    q = "untuk cabang paling tinggi tadi, tampilkan sell-out per bulannya"
    plan = plan_follow_up(q, ctx)
    assert plan is not None
    assert plan.to_grain is None
    assert plan.dimensions_override == ["calmonth"]
    assert plan.filter_entity is not None
    assert "Palembang" in str(plan.filter_entity["id"])
    res = try_follow_up_governed_resolution(q, ctx, _understanding_for_question(q, ctx))
    assert res is not None
    assert res["metric"] == "b2b_branch_sell_out_value"
    assert res["dimensions"] == ["calmonth"]


def test_follow_up_governed_resolution_b2b_material() -> None:
    ctx = build_analysis_context(
        metric="b2b_branch_sell_out_value",
        dimensions=["branch"],
        entity_dimension="branch",
        ranked_entities=[{"rank": 1, "dimension": "branch", "id": "DC Palembang", "metric_value": 1}],
        last_question="top 5 dc b2b",
    )
    q = "breakdown cabang palembang top 3 produk penjualan"
    u = _understanding_for_question(q, ctx)
    assert u is not None
    res = try_follow_up_governed_resolution(q, ctx, u)
    assert res is not None
    assert res["status"] == "resolved"
    assert res["metric"] == "b2b_branch_material_sell_out_value"
    assert res["dimensions"] == ["material"]
    assert res["matched_alias"] == "follow_up_context"
    assert res.get("dimension_mismatch") == []


def test_rewrite_follow_up_from_history() -> None:
    history = [
        {
            "question": "top 5 dc b2b",
            "strategy": "governed",
            "status": "SUCCESS",
            "session_frame": build_session_frame(
                question="top 5 dc b2b",
                status="SUCCESS",
                strategy="governed",
                rows=[{"branch": "DC Palembang", "metric_value": 1}, {"branch": "DC Makassar", "metric_value": 2}],
                metric="b2b_branch_sell_out_value",
                dimensions=["branch"],
            ),
            "rows": [{"branch": "DC Palembang", "metric_value": 1}],
        }
    ]
    ctx = analysis_context_from_history(history)
    q = "detail cabang palembang top 3 produk"
    u = _understanding_for_question(q, ctx)
    assert u is not None
    out = try_rewrite_follow_up_question(q, history, u)
    assert out is not None
    assert "DC Palembang" in out
    assert "follow-up" in out.casefold() or "prior" in out.casefold()


def test_contextualize_keeps_user_wording_for_governed_follow_up() -> None:
    from app.services.question_contextualize import governed_follow_up_keeps_literal_question

    history = [
        {
            "question": "Top 10 cabang Alfamart",
            "status": "SUCCESS",
            "strategy": "governed",
            "session_frame": build_session_frame(
                question="Top 10 cabang Alfamart",
                status="SUCCESS",
                strategy="governed",
                rows=[{"branch": "DC Palembang", "metric_value": 1}],
                metric="b2b_branch_sell_out_value",
                dimensions=["branch"],
            ),
            "rows": [{"branch": "DC Palembang", "metric_value": 1}],
        }
    ]
    q = "detail cabang palembang top 3 produk"
    ctx = analysis_context_from_history(history)
    u = _understanding_for_question(q, ctx)
    assert u is not None
    assert governed_follow_up_keeps_literal_question(q, history, understanding=u) is True


def test_analysis_context_from_history_rebuilds_from_rows_without_session_frame() -> None:
    history = [
        {
            "question": "top 5 dc b2b sell out",
            "strategy": "governed",
            "status": "SUCCESS",
            "session_frame": {},
            "rows": [
                {"branch": "DC Palembang", "metric_value": 1},
                {"branch": "DC Makassar", "metric_value": 2},
            ],
        }
    ]
    ctx = analysis_context_from_history(history)
    assert ctx.get("last_metric") == "b2b_branch_sell_out_value"
    assert ctx["result_catalog"][0]["id"] == "DC Palembang"


def test_analysis_context_from_history_skips_error_turn() -> None:
    history = [
        {
            "question": "top 5 dc",
            "strategy": "governed",
            "status": "SUCCESS",
            "rows": [{"branch": "DC Palembang", "metric_value": 1}, {"branch": "DC Makassar", "metric_value": 2}],
            "session_frame": {
                "last_metric": "b2b_branch_sell_out_value",
                "ranked_entities": [
                    {"rank": 1, "dimension": "branch", "id": "DC Palembang"},
                    {"rank": 2, "dimension": "branch", "id": "DC Makassar"},
                ],
                "analysis_context": {
                    "domain_id": "b2b",
                    "last_metric": "b2b_branch_sell_out_value",
                    "active_grain": "branch",
                    "result_catalog": [{"rank": 1, "entity_type": "branch", "id": "DC Palembang"}],
                    "last_question": "top 5 dc",
                },
            },
        },
        {"question": "oops", "status": "ERROR", "strategy": "unsupported", "rows": []},
    ]
    ctx = analysis_context_from_history(history)
    assert ctx.get("domain_id") == "b2b"
    assert ctx["result_catalog"][0]["id"] == "DC Palembang"
