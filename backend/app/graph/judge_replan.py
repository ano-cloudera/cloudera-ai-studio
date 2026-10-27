"""Map judge_review to workflow state updates (OSSIE path, bounded)."""

from __future__ import annotations

from typing import Any


def apply_judge_replan(state: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    decision = str(review.get("retry_decision") or "none")
    issues = list(review.get("issues") or [])
    update: dict[str, Any] = {
        "judge_review": review,
        "judge_issues": issues,
        "judge_iteration": int(state.get("judge_iteration") or 0) + 1,
    }
    if decision == "retry_synthesize":
        update["judge_retry_plan"] = False
        update["judge_retry_synthesize"] = True
        hints = "; ".join(issues[:3])
        update["judge_synthesis_hint"] = (
            f"Reviewer requested improvements: {hints}. Keep numbers identical to query_result; "
            "add grounded insights and business_implications where missing."
        )
    elif decision == "retry_plan":
        update["judge_retry_synthesize"] = False
        update["judge_retry_plan"] = True
        update["judge_plan_hint"] = issues[0] if issues else "Replan governed query for rank/limit."
    return update
