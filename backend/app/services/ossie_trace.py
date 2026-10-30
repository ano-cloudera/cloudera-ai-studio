"""Progress labels for OSSIE LangGraph stream (Phase C3)."""

from __future__ import annotations

from typing import Any

NODE_LABELS: dict[str, tuple[str, str]] = {
    "understand_request": ("understand", "Understanding your question"),
    "resolve_datasource": ("plan", "Resolving datasource"),
    "plan_query": ("plan", "Finding relevant data"),
    "validate_query": ("validate", "Validating the query"),
    "execute_query": ("query", "Fetching data"),
    "analyze_result": ("analyze", "Preparing insights"),
    "judge_answer": ("judge", "Quality review"),
}


def trace_detail(node: str, state: dict[str, Any]) -> str | None:
    if node == "resolve_datasource":
        ctx = state.get("datasource_context") or {}
        if ctx.get("connector_name") and ctx.get("connector_type"):
            return f"{ctx['connector_type']} · {ctx['connector_name']}"
        if ctx.get("legacy_fallback"):
            return "Legacy datasource"
    if node == "plan_query":
        plan = state.get("query_plan") or {}
        metrics = plan.get("metrics") or []
        resolution = state.get("semantic_resolution") or {}
        alias = resolution.get("matched_alias")
        governed_metric = resolution.get("metric")
        if metrics:
            detail = f"Metric: {', '.join(str(m) for m in metrics[:2])}"
            if governed_metric and str(governed_metric) not in detail:
                detail = f"{detail} · governed: {governed_metric}"
            if alias == "follow_up_context":
                detail = f"Follow-up · {detail}"
            return detail
        if governed_metric:
            detail = f"Governed metric: {governed_metric}"
            if alias == "follow_up_context":
                detail = f"Follow-up · {detail}"
            return detail
        if state.get("strategy") == "clarification":
            return "Needs metric clarification"
    if node == "validate_query":
        sql = (state.get("governed_sql") or "").strip()
        if sql:
            preview = " ".join(sql.split())
            if len(preview) > 100:
                preview = preview[:97] + "..."
            return preview
    if node == "analyze_result":
        resolution = state.get("semantic_resolution") or {}
        if resolution.get("status") == "resolved" and resolution.get("metric"):
            return f"Narrative from query result · {resolution['metric']}"
    if node == "execute_query":
        result = state.get("query_result") or {}
        count = result.get("row_count")
        if count is not None:
            return f"{count} row" if count == 1 else f"{count} rows"
    if node == "judge_answer":
        review = state.get("judge_review") or {}
        if review.get("accept"):
            return "OK"
        issues = review.get("issues") or []
        if issues:
            return issues[0][:120]
        replan = state.get("judge_retry_plan")
        if replan:
            return "Replan query"
    if node == "understand_request" and state.get("strategy") == "conversational":
        return "Conversational mode"
    return None
