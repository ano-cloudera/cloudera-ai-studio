from __future__ import annotations

from typing import Any, TypedDict


class AskDataState(TypedDict, total=False):
    request_id: str
    session_id: str
    question: str
    original_question: str
    conversation_history: list[dict[str, Any]]
    session_last_metric: str | None
    session_analysis_context: dict[str, Any]
    provider: str
    model: str
    use_local_agent: bool
    semantic_resolution: dict[str, Any]
    governed_partial_caveats: list[str]
    governed_entity_lookup: bool
    semantic_context: dict[str, Any]
    strategy: str
    query_plan: dict[str, Any]
    sql: str
    validated_sql: str
    validation_error: str
    query_result: dict[str, Any]
    answer: dict[str, Any]
    chart_spec: dict[str, Any] | None
    status: str
    error: str
    retry_count: int
    timings: dict[str, float]
    inquiry_brief: dict[str, Any]
    judge_iteration: int
    judge_review: dict[str, Any]
    judge_issues: list[str]
    judge_retry_synthesize: bool
    judge_synthesis_hint: str
    judge_retry_plan: bool
    judge_plan_hint: str
    conversational_intent: dict[str, Any]
    turn_understanding: dict[str, Any]
    skip_query_pipeline: bool
    runtime_mode: str
    semantic_version_id: str | None
    workspace_id: str | None
    project_id: str | None
    datasource_context: dict[str, Any]
    datasource_error: dict[str, Any]
    raw_table_policy: dict[str, Any]
    context_mode: str
