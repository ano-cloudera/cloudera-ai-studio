from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.text_sanitize import without_em_dash


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelInfo(StrictModel):
    provider: Literal["qwen", "gemini", "openai"]
    id: str
    label: str
    available: bool
    reason: str | None = None
    # The model the project assigned to Ask Data (Settings -> AI Models); it answers whatever the browser sends.
    assigned: bool = False


class ModelList(StrictModel):
    models: list[ModelInfo]


Status = Literal["SUCCESS", "CLARIFICATION", "clarification_required", "NO_DATA", "UNSUPPORTED", "ERROR"]
ContextMode = Literal["RAW_TABLE", "GOVERNED_SEMANTIC"]
QueryStrategy = Literal["governed", "sql_fallback", "clarification", "unsupported"]
Strategy = Literal[
    "governed",
    "sql_fallback",
    "clarification",
    "unsupported",
    "conversational",
    "rag",
    "mcp",
    "agent",
]
ChatMode = Literal["ask_data", "rag", "mcp"]
GroundingLevel = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE"]
ResponseRoute = Literal["ask_data", "rag"]
ChartType = Literal["bar", "line", "area", "scatter", "pie", "table", "kpi"]
PresentationTier = Literal[1, 2, 3]


class ChartSpec(StrictModel):
    type: ChartType
    # Gemini structured output rejects nested objects missing required keys.
    title: str = Field(default="Chart")
    x: str | None = None
    y: str | None = None
    series: str | None = None


class QueryPlan(StrictModel):
    strategy: QueryStrategy
    domains: list[str] = []
    metrics: list[str] = []
    dimensions: list[str] = []
    filters: dict[str, Any] = {}
    analysis_type: str = "metric"
    sql: str | None = None
    clarification_question: str | None = None


class AnalysisOutput(StrictModel):
    direct_answer: str
    executive_summary: str
    insights: list[str]
    business_implications: list[str]
    caveats: list[str]
    data_reference: str
    chart_spec: ChartSpec | None = None
    follow_up_questions: list[str] = Field(default_factory=list)  # what the reader could ask next, shown as chips

    @field_validator("follow_up_questions", mode="before")
    @classmethod
    def _clean_follow_ups(cls, value: object) -> object:
        if not isinstance(value, list):
            return []
        cleaned = [without_em_dash(" ".join(item.split())) for item in value if isinstance(item, str) and item.strip()]
        return list(dict.fromkeys(cleaned))[:3]

    @field_validator(
        "direct_answer",
        "executive_summary",
        "data_reference",
        mode="before",
    )
    @classmethod
    def _strip_em_dash_text(cls, value: object) -> object:
        return without_em_dash(value) if isinstance(value, str) else value

    @field_validator("insights", "business_implications", "caveats", mode="before")
    @classmethod
    def _strip_em_dash_lists(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [without_em_dash(item) if isinstance(item, str) else item for item in value]


class CitationRecord(StrictModel):
    document_id: str
    filename: str | None = None
    page_number: int | None = None
    section: str | None = None
    chunk_id: str
    source_uri: str | None = None
    snippet: str
    score: float


class RagRetrievalMeta(StrictModel):
    candidate_count: int = 0
    selected_count: int = 0


ChatContextSourceType = Literal[
    "knowledge_library",
    "uploaded_file",
    "mcp_connector",
    "table",
    "semantic_model",
    "semantic_entity",
    "semantic_metric",
    "semantic_term",
]


class ChatContextSource(StrictModel):
    type: ChatContextSourceType
    id: str
    name: str
    metadata: dict[str, Any] | None = None


class AskDataRequest(StrictModel):
    session_id: str
    question: str
    provider: Literal["qwen", "gemini", "openai"]
    model: str
    mode: ChatMode = "ask_data"
    library_ids: list[str] | None = None
    rag_document_ids: list[str] | None = None
    context_sources: list[ChatContextSource] | None = None
    # "llm" or "rules" for this request only (the judge compares both); empty uses the ASK_DATA_UNDERSTANDING setting.
    understanding: Literal["rules", "llm"] | None = None
    # "tools" or "plan" for this request only (the judge compares both); empty uses the AGENT_LOOP setting.
    agent_loop: Literal["tools", "plan"] | None = None
    # True for this request only: the agent answers every data question (AGENT_ANSWERS_ALL); the judge compares both.
    agent_all: bool | None = None


class QueryData(StrictModel):
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    execution_ms: float = 0
    governed_metric: str | None = None
    governed_metric_display_name: str | None = None
    metric_description: str | None = None  # what the metric measures, as its author wrote it, for chart readers
    metric_better: Literal["up", "down"] | None = None  # which way is good, when the author declared it
    metric_target: float | None = None  # the target the author declared, in the metric's own unit
    governed_metric_expression: str | None = None
    governed_base_dataset: str | None = None
    unit_format: str | None = None
    connector_type: str | None = None
    connector_name: str | None = None
    connector_id: str | None = None
    truncated: bool = False
    # Business names for the result columns ("delivery_shipments_region_name" -> "Region").
    column_labels: dict[str, str] = {}
    # The same metric over the same filters and period without the breakdown, when the answer is a breakdown.
    overall_value: float | None = None
    # Where the values of a result column are, when its dimension carries coordinates: {column: {value: [latitude, longitude]}}.
    geo_points: dict[str, dict[str, list[float]]] = {}
    # The first and last date the dataset holds ({"first": "2026-01-01", "last": "2026-08-31"}).
    data_coverage: dict[str, str] | None = None


class Timings(StrictModel):
    context_ms: float = 0
    planning_ms: float = 0
    validation_ms: float = 0
    query_ms: float = 0
    datasource_ms: float = 0
    analysis_ms: float = 0
    total_ms: float = 0


class LlmUsage(StrictModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0


class SemanticRuntimeMeta(StrictModel):
    mode: str
    deployment_id: str | None = None
    semantic_version_id: str | None = None
    registry_version_number: int | None = None
    artifact_checksum: str | None = None
    health: str | None = None


class ClarificationOption(StrictModel):
    type: ChatContextSourceType
    id: str
    name: str


class AskDataClarification(StrictModel):
    reason: str
    message: str
    options: list[ClarificationOption] = []


class ModelResolutionMeta(StrictModel):
    capability: str | None = None
    assignment_source: str | None = None
    provider_type: str | None = None
    model_key: str | None = None
    registry_model_id: str | None = None
    model_name: str | None = None  # as named in Settings -> AI Models; the answer footer shows it
    provider_name: str | None = None


class CalculationCheck(StrictModel):
    name: str
    status: Literal["ok", "warning"]
    message: str


class CalculationNote(StrictModel):
    """How an answer was reached, built from the query plan and the executed SQL, never from the model's text."""

    kind: Literal["governed", "comparison", "fallback", "agent"] = "governed"
    summary: str
    metric: str | None = None
    formula: str | None = None
    breakdown: list[str] = []
    filters: list[str] = []
    period: str | None = None
    source: list[str] = []
    comparison: str | None = None
    scope: str | None = None  # one plain sentence on what the figures cover, in the language of the question
    steps: list[str] = []
    checks: list[CalculationCheck] = []


class ProposedAction(StrictModel):
    """An action the agent proposes (an MCP tool that changes something); it runs only when the user approves it."""

    id: str
    server_id: str
    server: str
    tool: str
    title: str
    arguments: dict[str, Any] = {}


class AgentStepCard(StrictModel):
    """One check the agent made, shown in the chat as it works and after: what it looked at, how it went, a few rows."""

    title: str
    tool: str
    status: Literal["ok", "no_data", "failed"]
    row_count: int = 0
    columns: list[str] = []
    column_labels: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    unit_format: str | None = None
    overall_value: float | None = None
    sql: str | None = None
    sources: list[dict[str, Any]] = []


class AskDataResponse(StrictModel):
    request_id: str
    session_id: str
    status: Status
    provider: str
    model: str
    strategy: Strategy
    answer: AnalysisOutput
    data: QueryData
    chart_spec: ChartSpec | None
    timings: Timings
    retry_count: int = 0
    usage: LlmUsage | None = None
    governed_sql: str | None = None
    route: ResponseRoute | None = None
    grounding: GroundingLevel | None = None
    citations: list[CitationRecord] | None = None
    retrieval: RagRetrievalMeta | None = None
    semantic_runtime: SemanticRuntimeMeta | None = None
    model_resolution: ModelResolutionMeta | None = None
    # When the answer came from the answer cache: when it was computed (ISO), and whether because the data source failed.
    cached_at: str | None = None
    cache_reason: Literal["repeat", "data_source_unavailable"] | None = None
    language: Literal["id", "en"] | None = None  # the language of the question, so the UI names its sections in it
    proposed_actions: list[ProposedAction] | None = None
    analysis_report: str | None = None  # the agent's full analysis (markdown), shown in the panel; the chat shows its summary
    agent_steps: list[AgentStepCard] | None = None  # the checks behind an agent's answer, in the order they ran  # actions the agent proposes, each approved by the user before it runs
    context_mode: ContextMode | None = None
    clarification: AskDataClarification | None = None
    presentation_tier: PresentationTier | None = None
    calculation: CalculationNote | None = None
