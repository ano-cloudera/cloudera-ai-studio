"""Answer reviewer for OSSIE governed workflow (deterministic gates)."""

from __future__ import annotations

import re
from typing import Any


def deterministic_judge(state: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    brief = state.get("inquiry_brief") or {}
    answer = state.get("answer") or {}
    plan = state.get("query_plan") or {}
    sql = str(state.get("validated_sql") or state.get("sql") or "")
    result = state.get("query_result") or {}
    row_count = int(result.get("row_count") or 0)

    exp_metric = str(brief.get("expected_metric") or "")
    plan_metrics = [str(m) for m in plan.get("metrics") or []]
    if exp_metric and plan_metrics and exp_metric not in plan_metrics:
        issues.append(f"Measure mismatch: inquiry expects {exp_metric}, plan used {plan_metrics[0]}.")

    if brief.get("wants_rank") and sql:
        if "order by" not in sql.lower():
            issues.append("Rank/top-N requested but SQL has no ORDER BY.")
        if brief.get("rank_limit") and "limit" not in sql.lower():
            issues.append(f"Top-{brief.get('rank_limit')} requested but SQL has no LIMIT.")
        limit = brief.get("rank_limit")
        if limit and row_count > 0 and row_count < int(limit) and int(limit) >= 5:
            issues.append(
                f"Rank/top-{limit} requested but query returned only {row_count} row(s); check breakdown grain (e.g. dcname)."
            )

    if row_count == 0 and str(state.get("status")) == "SUCCESS":
        issues.append("SUCCESS status but query returned zero rows.")

    if row_count > 0:
        ref = str(answer.get("data_reference") or "")
        if ref and "gold." not in ref.lower() and not ref.startswith("TEMPO Local Agent"):
            issues.append("Executed rows present but data_reference lacks gold view citation.")

    direct = str(answer.get("direct_answer") or "").strip()
    if not direct:
        issues.append("Empty direct_answer.")

    if brief.get("wants_operational_analysis"):
        insights = list(answer.get("insights") or [])
        implications = list(answer.get("business_implications") or [])
        if not insights and not implications:
            issues.append("Operational analysis requested but insights/implications are empty.")

    if brief.get("resolver_status") == "needs_clarification" and str(state.get("strategy")) == "governed":
        issues.append("Resolver needed clarification but governed plan was executed anyway.")

    return issues


def judge_fast_path_accept(state: dict[str, Any]) -> bool:
    """Skip replan/re-synthesize when governed path already returned usable rows."""
    brief = state.get("inquiry_brief") or {}
    if brief.get("wants_operational_analysis"):
        return False
    if str(state.get("strategy")) not in ("governed", "sql_fallback"):
        return False
    if str(state.get("status")) != "SUCCESS":
        return False
    row_count = int((state.get("query_result") or {}).get("row_count") or 0)
    if row_count <= 0:
        return False
    resolution = state.get("semantic_resolution") or {}
    if resolution.get("status") != "resolved":
        return False
    sql = str(state.get("validated_sql") or state.get("sql") or "").casefold()
    if brief.get("wants_rank"):
        if "order by" not in sql or "limit" not in sql:
            return False
    direct = str((state.get("answer") or {}).get("direct_answer") or "").strip()
    if not direct:
        return False
    return True


def judge_review(state: dict[str, Any], *, max_iterations: int = 2) -> dict[str, Any]:
    if judge_fast_path_accept(state):
        return {
            "accept": True,
            "issues": [],
            "retry_decision": "none",
            "judge_iteration": int(state.get("judge_iteration") or 0),
            "retry_allowed": False,
        }
    issues = deterministic_judge(state)
    iteration = int(state.get("judge_iteration") or 0)
    accept = not issues
    retry_decision = "none"
    if not accept:
        if any("Operational analysis" in i for i in issues):
            retry_decision = "retry_synthesize"
        elif iteration < max_iterations and any(
            k in " ".join(issues).lower() for k in ("measure mismatch", "order by", "limit")
        ):
            retry_decision = "retry_plan"
        elif iteration < max_iterations:
            retry_decision = "retry_synthesize"
    return {
        "accept": accept,
        "issues": issues,
        "retry_decision": retry_decision,
        "judge_iteration": iteration,
        "retry_allowed": (not accept) and iteration < max_iterations and retry_decision != "none",
    }
